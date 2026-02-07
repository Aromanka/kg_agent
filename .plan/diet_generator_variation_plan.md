当前LLM生成方案过于单一问题在于：

1. **策略/菜系指令过粗**：仅仅告诉 LLM “地中海”或“高纤维”，它倾向于输出训练数据中该类别下概率最高的组合（即“安全牌”：鸡胸肉、西兰花、糙米）。
2. **Prompt 示例的锚定效应**：System Prompt 中的示例（Oatmeal, Egg）可能限制了模型的想象力。
3. **参数 Temperature 仍不够**：或者在某些实现中未生效。

**改进方案：强制性成分注入 (Mandatory Ingredient Injection)**
不再依赖 LLM “自由发挥”选择食材，而是在 Python 代码层面**随机抽取核心食材**，并以“约束条件”的形式强制写入 Prompt。同时，**随机禁用**某些高频食材（如鸡胸肉）。

此外，日志显示 `calories_per_unit` 存在严重幻觉（如西兰花 25kcal/g，实际约 0.34kcal/g），这会导致安全检查失败。我将在 Prompt 中修正这一点，改为让 LLM 输出该份量的**总热量**，准确率会大幅提升。

### 1. 修改 `agents/diet/generator.py`

在生成逻辑中加入食材池和随机抽取逻辑。

```python
"""
Diet Candidate Generator (Enhanced with Ingredient Injection)
"""
import json
import random
from typing import List, Dict, Any, Optional
from agents.base import BaseAgent, DietAgentMixin
from agents.diet.models import DietRecommendation, DietAgentInput
from agents.diet.prompts import DIET_GENERATION_SYSTEM_PROMPT # 确保引用更新后的Prompt
from core.llm.utils import parse_json_response

# 定义丰富的食材池
PROTEIN_SOURCES = [
    "Cod Fillet", "Salmon", "Tofu", "Lean Beef Steak", "Shrimp", 
    "Turkey Breast", "Pork Tenderloin", "Lamb Chop", "Edamame", "Tempeh",
    "Duck Breast", "Tuna Steak", "Sardines", "Chickpeas"
]

CARB_SOURCES = [
    "Quinoa", "Sweet Potato", "Buckwheat", "Whole Wheat Pasta", "Couscous", 
    "Barley", "Corn", "Multigrain Bread", "Red Potato", "Wild Rice",
    "Polenta", "Bulgur", "Millet"
]

VEG_SOURCES = [
    "Asparagus", "Spinach", "Kale", "Zucchini", "Bell Peppers", 
    "Eggplant", "Cauliflower", "Green Beans", "Brussels Sprouts", 
    "Bok Choy", "Artichokes", "Mushrooms", "Snow Peas"
]

COMMON_BORING_FOODS = ["Chicken Breast", "Brown Rice", "Broccoli", "Boiled Egg"]

class DietAgent(BaseAgent, DietAgentMixin):
    # ... (保留 get_agent_name, get_input_type, get_output_type) ...

    def generate(self, input_data: Dict[str, Any], num_candidates: int = 3) -> List[DietRecommendation]:
        # ... (保留 Input 解析和 target_calories 计算逻辑) ...
        # ... (保留 KG Context 逻辑) ...
        
        candidates = []
        used_combinations = set()

        for i in range(num_candidates):
            # 1. 随机抽取核心食材 (Hero Ingredients)
            protein = random.choice(PROTEIN_SOURCES)
            carb = random.choice(CARB_SOURCES)
            veg = random.choice(VEG_SOURCES)
            
            # 2. 随机决定是否禁用“无聊”食材 (50% 概率)
            excluded = []
            if random.random() > 0.5:
                excluded = random.sample(COMMON_BORING_FOODS, k=random.randint(1, 2))

            # 3. 避免生成重复组合
            combo_key = f"{protein}-{carb}"
            if combo_key in used_combinations and num_candidates < len(PROTEIN_SOURCES):
                continue
            used_combinations.add(combo_key)

            # 4. 构建包含强制约束的 Prompt
            constraint_prompt = self._build_constraint_prompt(protein, carb, veg, excluded)
            
            # 5. 生成
            user_prompt = self._build_diet_prompt(
                user_meta=input_obj.user_metadata,
                environment=input_obj.environment,
                requirement=input_obj.user_requirement,
                target_calories=target_calories,
                kg_context=kg_context
            )
            
            full_prompt = user_prompt + "\n" + constraint_prompt

            candidate = self._generate_single_candidate(
                full_prompt, 
                i + 1,
                cuisine=random.choice(["Mediterranean", "Asian", "Western", "Fusion", "Latin"]) # 随机菜系
            )
            
            if candidate:
                candidates.append(candidate)
        
        return candidates

    def _build_constraint_prompt(self, protein, carb, veg, excluded):
        prompt = "\n## Mandatory Ingredients (You MUST use these):\n"
        prompt += f"- Main Protein: {protein}\n"
        prompt += f"- Carb Source: {carb}\n"
        prompt += f"- Vegetable: {veg}\n"
        
        if excluded:
            prompt += f"\n## Excluded Ingredients (Do NOT use):\n- {', '.join(excluded)}\n"
            
        return prompt

    def _generate_single_candidate(self, user_prompt: str, candidate_id: int, cuisine: str) -> Optional[DietRecommendation]:
        # 添加菜系风格提示
        full_prompt = user_prompt + f"\n\n### Culinary Style: {cuisine}\nPrepare the mandatory ingredients in {cuisine} style."
        
        # 提高 Temperature 到 0.9 以增加多样性
        response = self._call_llm(
            system_prompt=DIET_GENERATION_SYSTEM_PROMPT,
            user_prompt=full_prompt,
            temperature=0.9
        )
        
        # ... (保留解析逻辑) ...
        # 注意：这里需要根据新的 Prompt 输出格式（total_calories）调整解析或由 Parser 处理
        # ...
        return DietRecommendation(**plan_data)

```

### 2. 修改 `agents/diet/prompts.py`

修正 System Prompt：

1. **移除 `calories_per_unit**`：LLM 对“每单位热量”的计算非常糟糕（如日志中的西兰花 25kcal/g）。改为输出 `total_calories`（该份食物的总热量），LLM 对此估算更准。
2. **通用化示例**：避免使用具体的食物名称作为 Example，防止 LLM 模仿。

```python
DIET_GENERATION_SYSTEM_PROMPT = """You are a professional nutritionist. Generate BASE meal plans with standardized portions.

## Output Format
Output MUST be a valid JSON list of objects. Each object is a food item with these fields:
- "food_name": string (Name of the food, e.g., "Grilled Salmon")
- "portion_number": number (Numeric quantity, e.g., 150, 1.5)
- "portion_unit": string (MUST be one of: ["gram", "ml", "piece", "slice", "cup", "bowl", "spoon"])
- "total_calories": number (Total calories for THIS portion size. E.g., for 150g salmon, output ~300)

## Rules
1. Use ONLY the allowed units listed above.
2. STRICTLY follow the "Mandatory Ingredients" and "Excluded Ingredients" in the user prompt.
3. Estimate "total_calories" realistically (e.g., Vegetables are low calorie, Oils are high calorie).
4. Do NOT wrap in extra keys like "meal_plan".
5. Do NOT output markdown code blocks.

## Example Output:
[
  {
    "food_name": "Pan-Seared Cod",
    "portion_number": 150,
    "portion_unit": "gram",
    "total_calories": 157
  },
  {
    "food_name": "Quinoa Salad",
    "portion_number": 1,
    "portion_unit": "bowl",
    "total_calories": 220
  },
  {
    "food_name": "Olive Oil",
    "portion_number": 5,
    "portion_unit": "ml",
    "total_calories": 40
  }
]
"""

```

### 3. 后续处理建议 (Parser)

由于我们将输出字段改为了 `total_calories`，您需要在 `agents/diet/parser.py` 或 `generator.py` 的解析逻辑中做一个简单的适配：

```python
# 在 generator.py 解析后，或者 parser.py 扩展前
# 如果需要 unit_calories 用于扩展计算：
unit_calories = item['total_calories'] / item['portion_number']

```

这种“强制注入”策略能确保：

1. **绝对的多样性**：因为 Python 随机选择了“三文鱼”和“藜麦”，LLM 不可能再生成“鸡胸肉”和“糙米”。
2. **规避幻觉**：通过让 LLM 估算总热量（它见过的常见搭配）而非单位密度热量（数学计算），能减少 1000% 偏差这类严重错误。