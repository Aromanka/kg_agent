为了解决 `pipeline.diet_pipeline` 每次生成的方案过于相似的问题，我们需要在生成过程中引入**随机性变量**（Randomness/Entropy）。目前的实现中，Prompt 的内容对于相同的用户输入是固定的，且策略（Strategy）是按固定顺序循环的，这导致 LLM 在相同的上下文下倾向于输出相似的结果。

以下是具体的改进方案：

### 核心改进思路

1. **引入随机“风格/菜系” (Cuisine/Theme)**：在生成时随机注入不同的饮食风格（如地中海、亚洲、西式等），强制模型在食材选择和烹饪方式上做出改变。
2. **策略随机化 (Randomize Strategy)**：不再按固定顺序 `(i % 3)` 选择策略，而是从策略池中随机抽取。
3. **提升 Temperature**：微调 LLM 的 Temperature 参数，增加输出的多样性。

### 代码修改方案

我们需要修改 `agents/diet/generator.py` 文件。

#### 1. 修改 `agents/diet/generator.py`

请按以下步骤更新代码：

1. 引入 `random` 模块。
2. 在 `generate` 方法中增加随机选择 **Strategy** 和 **Cuisine** 的逻辑。
3. 在 `_generate_single_candidate` 方法中将这些随机因子加入 Prompt。

```python
"""
Diet Candidate Generator (Improved for Diversity)
"""
import json
import random  # [新增] 引入 random 模块
from typing import List, Dict, Any, Optional
from agents.base import BaseAgent, DietAgentMixin
from agents.diet.models import DietRecommendation, DietAgentInput
from core.llm.utils import parse_json_response

# ... (保留原有的 SYSTEM_PROMPT 和 imports) ...

class DietAgent(BaseAgent, DietAgentMixin):
    """Agent for generating diet recommendation candidates"""
    
    # ... (保留 get_agent_name, get_input_type, get_output_type 方法) ...

    def generate(
        self,
        input_data: Dict[str, Any],
        num_candidates: int = 3
    ) -> List[DietRecommendation]:
        """Generate diet plan candidates with high diversity"""
        # Parse input
        input_obj = DietAgentInput(**input_data)
        
        user_meta = input_obj.user_metadata
        env = input_obj.environment
        requirement = input_obj.user_requirement

        # ... (保留 target_calories 和 kg_context 计算逻辑) ...
        # Calculate target calories
        target_calories = self.calculate_target_calories(
            age=user_meta.get("age", 30),
            gender=user_meta.get("gender", "male"),
            height_cm=user_meta.get("height_cm", 170),
            weight_kg=user_meta.get("weight_kg", 70),
            goal=requirement.get("goal", "maintenance"),
            activity_factor=self._get_activity_factor(user_meta.get("fitness_level", "beginner"))
        )
        
        # Get KG context
        kg_context = ""
        conditions = user_meta.get("medical_conditions", [])
        if conditions:
            dietary_knowledge = self.query_dietary_knowledge(
                conditions, user_meta.get("dietary_restrictions", [])
            )
            kg_context = self._format_kg_context(dietary_knowledge)

        # Build user prompt
        user_prompt = self._build_diet_prompt(
            user_meta=user_meta,
            environment=env,
            requirement=requirement,
            target_calories=target_calories,
            kg_context=kg_context
        )

        # [新增] 定义多样性池
        available_strategies = ["balanced", "protein_focus", "variety", "low_carb", "fiber_rich"]
        available_cuisines = ["Mediterranean", "Asian", "Western", "Fusion", "Local Home-style", "Simple & Quick"]
        
        # Generate candidates
        candidates = []
        used_strategies = set() # 避免单次生成中策略过度重复

        for i in range(num_candidates):
            # [改进] 随机选择策略，尽量不重复
            remaining_strategies = [s for s in available_strategies if s not in used_strategies]
            if not remaining_strategies:
                remaining_strategies = available_strategies
            
            strategy = random.choice(remaining_strategies)
            used_strategies.add(strategy)
            
            # [改进] 随机选择菜系/风格
            cuisine = random.choice(available_cuisines)

            candidate = self._generate_single_candidate(
                user_prompt=user_prompt,
                candidate_id=i + 1,
                strategy=strategy,
                cuisine=cuisine  # 传入 cuisine 参数
            )
            if candidate:
                candidates.append(candidate)

        # Sort by calorie deviation
        candidates.sort(key=lambda x: abs(x.calories_deviation))

        return candidates

    # ... (保留 _get_activity_factor, _format_kg_context, _build_diet_prompt 方法) ...

    def _generate_single_candidate(
        self,
        user_prompt: str,
        candidate_id: int,
        strategy: str = "balanced",
        cuisine: str = "General"  # [新增] 参数
    ) -> Optional[DietRecommendation]:
        """Generate a single diet candidate with style injection"""
        
        strategy_guidance = {
            "balanced": "Focus on balanced nutrition across all macros.",
            "protein_focus": "Emphasize high-protein foods for muscle maintenance.",
            "variety": "Include diverse food types and colors.",
            "low_carb": "Reduce carbohydrate intake slightly, focus on quality fats and proteins.",
            "fiber_rich": "Prioritize high-fiber vegetables and whole grains."
        }

        # [改进] 构建更具独特性的 Prompt
        full_prompt = user_prompt + f"\n\n### Optimization Strategy: {strategy.upper()}\n{strategy_guidance.get(strategy, '')}"
        full_prompt += f"\n\n### Culinary Style: {cuisine}\nPLEASE strictly follow this style. Use ingredients and cooking methods typical for {cuisine} cuisine."

        # [改进] 稍微提高 Temperature 增加随机性 (从 0.7 提至 0.85)
        response = self._call_llm(
            system_prompt=DIET_GENERATION_SYSTEM_PROMPT,
            user_prompt=full_prompt,
            temperature=0.85 
        )

        # Handle empty response
        if not response or response == {}:
            print(f"[WARN] LLM returned empty response for candidate {candidate_id}")
            return None

        try:
            data = parse_json_response(response)
        except json.JSONDecodeError:
            print(f"[WARN] Invalid JSON from LLM: {response[:100]}...")
            return None

        # ... (保留后续的数据解析逻辑) ...
        
        # Handle list response
        if isinstance(data, list):
            plan_data = data[0] if data else {}
        elif isinstance(data, dict):
            plan_data = data
        else:
            return None

        # Ensure ID
        if "id" not in plan_data:
            plan_data["id"] = candidate_id

        # 可以在 safety_notes 中记录风格，方便调试
        if "safety_notes" not in plan_data:
            plan_data["safety_notes"] = []
        plan_data["safety_notes"].append(f"Style: {cuisine}, Strategy: {strategy}")

        return DietRecommendation(**plan_data)

```

### 为什么这样做有效？

1. **Prompt 差异化**：现在的 Prompt 每次都会包含例如 `Culinary Style: Asian` 或 `Culinary Style: Mediterranean` 的指令。LLM 必须根据这个指令生成具体的食物（例如“亚洲”会生成米饭、豆腐，“地中海”会生成橄榄油、鱼类），从而从根本上避免了方案雷同。
2. **Temperature 提升**：将 Temperature 提高到 `0.85` 会让模型在选择下一个 Token 时更具冒险性，减少“千篇一律”的概率。
3. **策略池扩展**：增加了 `low_carb` 和 `fiber_rich` 等策略，使得营养分配的侧重点也会发生变化。

应用此修改后，再次运行 `python -m pipeline.diet_pipeline`，您应该能看到生成的 3 个候选方案在食物选择和风格上有显著的差异。