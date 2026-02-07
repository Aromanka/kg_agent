需要对现有的 `agents/diet` 模块进行重构。核心思路是将原本由 LLM “一步到位”生成完整方案和营养分析的过程，拆解为 **“LLM 生成基准方案” + “Python 解析器规则扩展”** 两步走。

以下是针对 `kg_agent` 项目的具体改进方案：

### 1. 数据模型定义 (`agents/diet/models.py`)

首先，我们需要定义符合您要求的“基准食物”模型，以及用于约束单位的枚举。

```python
from pydantic import BaseModel, Field
from typing import List, Literal

# 1. 定义允许的单位列表（与 Prompt 保持一致）
ALLOWED_UNITS = Literal["gram", "ml", "piece", "slice", "cup", "bowl", "spoon"]

class BaseFoodItem(BaseModel):
    """LLM 输出的基准食物项"""
    food_name: str = Field(..., description="食物名称")
    portion_number: float = Field(..., description="数字数量，纯数字")
    portion_unit: ALLOWED_UNITS = Field(..., description="数量单位")
    # 建议保留基础热量/营养字段，以便后续按比例扩展
    # base_calories: float = Field(..., description="该数量下的估算热量") 

class RawDietPlan(BaseModel):
    """LLM 输出的一次 Plan（基准）"""
    items: List[BaseFoodItem]

```

### 2. Prompt 工程改进 (`agents/diet/prompts.py`)

修改 System Prompt，强制要求输出指定的 JSON 格式，并注入单位限制。

```python
# 定义单位列表字符串，嵌入 Prompt
UNIT_LIST_STR = '["gram", "ml", "piece", "slice", "cup", "bowl", "spoon"]'

DIET_GENERATION_SYSTEM_PROMPT = f"""You are a professional nutritionist. Generate a meal plan based on user requirements.

## Output Format Requirements
1. Output MUST be a valid JSON list of objects.
2. Each object represents a food item and MUST contain exactly these fields:
   - "food_name": string (Name of the food)
   - "portion_number": float or int (Pure number, e.g., 100, 1.5)
   - "portion_unit": string (MUST be chosen from: {UNIT_LIST_STR})

## Example Output
[
  {{
    "food_name": "Oatmeal",
    "portion_number": 50,
    "portion_unit": "gram"
  }},
  {{
    "food_name": "Boiled Egg",
    "portion_number": 1,
    "portion_unit": "piece"
  }}
]

## Task
Generate a SINGLE meal plan consisting of multiple food items suitable for the user's profile.
Do NOT output multiple plans. Do NOT output markdown code blocks. Just the JSON list.
"""

```

### 3. 新增解析器组件 (`agents/diet/parser.py`)

这是本次改进的核心。我们需要实现一个解析器，根据单位规则（Rules）对 LLM 生成的基准方案进行“裂变”扩展。

```python
from typing import List, Dict, Any
import copy
from .models import BaseFoodItem

class DietPlanParser:
    """
    饮食方案解析与扩展器
    功能：将一个基准 Plan 扩展为多个不同分量的 Plan
    """

    def __init__(self):
        # 定义扩展规则：(最小系数, 最大系数, 步长) 或 (固定增减量)
        self.expansion_rules = {
            "gram": [0.8, 1.0, 1.2],   # 克重：生成 80%, 100%, 120% 三种分量
            "ml": [0.8, 1.0, 1.2],     # 毫升：同上
            "piece": [0, 1],           # 个/片：保持原样 或 +1 (需结合具体逻辑)
            "slice": [-1, 0, 1],       # 切片：减一片、保持、加一片
            "cup": [0.5, 1.0, 1.5],    # 杯：半杯、一杯、一杯半
            "bowl": [0.8, 1.0, 1.2],
            "spoon": [1.0]             # 勺：通常作为调料，不建议大幅调整，保持原样
        }

    def expand_plan(self, base_items: List[BaseFoodItem]) -> List[List[Dict[str, Any]]]:
        """
        核心逻辑：根据规则生成多个 Plan 变体。
        策略：这里采用“整体缩放”策略，即生成“小份量版”、“标准版”、“大份量版”。
        """
        expanded_plans = []
        
        # 定义三种缩放级别：轻量(Lite), 标准(Standard), 增量(Plus)
        # 这里演示的是基于系数的整体缩放
        scales = {
            "Lite": 0.8,
            "Standard": 1.0,
            "Plus": 1.2
        }

        for level_name, scale_factor in scales.items():
            new_plan = []
            for item in base_items:
                # 1. 复制对象
                new_item = item.model_dump()
                
                # 2. 计算新数量
                current_unit = new_item['portion_unit']
                original_num = new_item['portion_number']
                
                final_num = original_num
                
                # 3. 应用单位特定的规则
                if current_unit in ["gram", "ml"]:
                    # 连续量：直接乘系数
                    final_num = original_num * scale_factor
                    # 取整，保留1位小数
                    final_num = round(final_num, 1)
                    
                elif current_unit in ["piece", "slice", "cup", "bowl"]:
                    # 离散量：处理逻辑稍微复杂
                    if scale_factor < 1.0:
                        final_num = max(0.5, original_num - 0.5) # 最小减半
                    elif scale_factor > 1.0:
                        final_num = original_num + 0.5 # 加半个
                    else:
                        final_num = original_num
                
                new_item['portion_number'] = final_num
                # 可以在这里标记这是什么版本的方案
                new_item['_meta_tag'] = level_name 
                
                new_plan.append(new_item)
            
            expanded_plans.append(new_plan)
            
        return expanded_plans

    # 备选：如果需要排列组合（例如A多B少，A少B多），可以使用 itertools.product
    # 但这会导致生成的方案数量指数级爆炸，建议使用上述“整体缩放”策略。

```

### 4. 集成到 Generator (`agents/diet/generator.py`)

修改 `DietAgent` 的 `generate` 方法，串联 LLM 调用和解析器。

```python
# ... 引入依赖 ...
from .parser import DietPlanParser
from .models import RawDietPlan, DietRecommendation

class DietAgent(BaseAgent, DietAgentMixin):
    # ... 其他方法保持不变 ...

    def __init__(self):
        super().__init__()
        self.parser = DietPlanParser()

    def generate(self, input_data: Dict[str, Any], num_candidates: int = 3) -> List[DietRecommendation]:
        """
        改进后的生成流程：
        1. LLM 生成一个基准 Plan (Raw JSON)
        2. Parser 将其裂变为多个 Plan
        3. 封装为 DietRecommendation 对象
        """
        # ... (省略 input 解析和 prompt 构建部分，这部分逻辑复用之前的) ...
        
        # 1. 调用 LLM 获取基准方案 (只生成 1 次 LLM 调用即可，因为我们要裂变)
        # 注意：Prompt 中要求生成的是 List[BaseFoodItem]
        raw_response = self._call_llm(
            system_prompt=DIET_GENERATION_SYSTEM_PROMPT,
            user_prompt=full_prompt, # 您的 prompt 构建逻辑
            temperature=0.7
        )
        
        # 解析 LLM 的 JSON
        try:
            # 假设 utils.parse_json_response 能返回 list
            raw_data = parse_json_response(raw_response) 
            # 校验数据结构
            base_items = [BaseFoodItem(**item) for item in raw_data]
        except Exception as e:
            print(f"Error parsing LLM output: {e}")
            return []

        # 2. 调用解析器进行扩展
        # 输入：[Item1, Item2]
        # 输出：[[Item1_Lite, Item2_Lite], [Item1_Std, Item2_Std], [Item1_Plus, Item2_Plus]]
        expanded_plans_data = self.parser.expand_plan(base_items)

        # 3. 转换为最终的 Candidate 对象列表
        candidates = []
        for idx, plan_data in enumerate(expanded_plans_data):
            # 注意：因为 LLM 现在只输出名称和数量，没有热量。
            # 这里需要一个计算逻辑：要么根据数量重新估算热量，要么让 LLM 最初就输出每单位热量。
            # 为了适配现有 Pipeline 的 check，这里做一个简化的热量估算占位
            
            total_cals, macros = self._calculate_macros_heuristically(plan_data)
            
            candidate = DietRecommendation(
                id=idx + 1,
                meal_plan={"generated_meal": plan_data}, # 适配原有结构
                total_calories=total_cals,
                calories_deviation=0.0, # 需根据 target 计算
                macro_nutrients=macros,
                safety_notes=[f"Variation: {plan_data[0].get('_meta_tag', 'Standard')}"]
            )
            candidates.append(candidate)

        # 截取需要的数量
        return candidates[:num_candidates]

    def _calculate_macros_heuristically(self, items: List[Dict]) -> tuple:
        """
        由于解析器改变了数量，原本 LLM 输出的总热量失效。
        需要一个简单的估算器，或者依赖 KG 里的数据查询食物单位热量。
        这里仅做示例桩代码。
        """
        # 实际项目中，建议在 BaseFoodItem 让 LLM 输出 'calories_per_unit'
        # 然后在这里用 quantity * calories_per_unit 计算
        return 1000, {"protein": 0, "carbs": 0, "fat": 0} # Placeholder

```

### 方案总结与注意事项

1. **明确分工**：
* **LLM**：只负责“吃什么”和“大概吃多少（基准单位）”，不再负责生成多个方案，减轻了 LLM 的 Context 压力。
* **Parser**：负责“吃多少的变化”，通过确定性的算法（Rules）生成不同热量等级的方案（如减脂版、维持版、增肌版）。


2. **单位一致性**：
* Prompt 中强制限制了 `portion_unit` 的取值范围，这对于 Parser 的 `if-else` 逻辑至关重要。如果 LLM 输出了 "box" 或 "handful" 这种不在规则内的单位，Parser 应当有 fallback 逻辑（如默认不调整数量）。


3. **热量计算（Missing Link）**：
* 目前的方案中，LLM 输出纯粹的食物和数量。原有的 `DietRecommendation` 需要 `total_calories` 来进行 `Safeguard` 检查。
* **建议补充**：在 Prompt 中要求 LLM 额外输出一个字段 `calories_per_unit` (单位热量)。这样 Parser 在调整 `portion_number` 后，可以简单地通过 `new_number * calories_per_unit` 算出新方案的准确热量，从而使得整个 Pipeline 的安全校验依然有效。