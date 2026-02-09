import json
import random
import re
from typing import List, Dict, Any, Optional
from agents.base import BaseAgent, DietAgentMixin
from agents.diet.models import (
    FoodItem,
    DietRecommendation, DietAgentInput,
    BaseFoodItem
)
from agents.diet.parser import DietPlanParser
from core.llm.utils import parse_json_response
from agents.diet.config import *


DIET_GENERATION_SYSTEM_PROMPT = f"""You are a professional nutritionist. Generate BASE meal plans with standardized portions.

## Output Format
Output MUST be a valid JSON list of objects. Each object is a food item with these fields:
- "food_name": string (Name of the food, e.g., "Grilled Salmon")
- "portion_number": number (Numeric quantity, e.g., 150, 1.5)
- "portion_unit": string (MUST be one of: {UNIT_LIST_STR} - "spoon" is for teaspoons, NOT "teaspoon")
- "total_calories": number (TOTAL calories for the ENTIRE portion. E.g., 150g salmon = ~200 kcal total, 1 bowl rice = ~250 kcal total)

## Rules
1. Use ONLY the allowed units listed above - "spoon" means teaspoon (5ml), NOT "teaspoon"
2. STRICTLY follow the "Mandatory Ingredients" and "Excluded Ingredients" in the user prompt
3. "total_calories" must be the TOTAL calories for the whole portion, NOT per unit
4. Realistic calorie references:
   - 100g meat/fish: ~150-200 kcal total
   - 100g vegetables: ~20-50 kcal total
   - 100g carbs (rice/potato): ~130-150 kcal total
   - 1 bowl (300g): ~200-300 kcal total
   - 1 piece fruit: ~50-100 kcal total
   - 5ml oil: ~45 kcal total
5. CRITICAL: If you output 120g Tempeh, total_calories should be ~200-250, NOT 14000
6. Output food items for ONE meal type as a JSON LIST
7. Do NOT wrap in extra keys like "meal_plan" or "items"
8. Do NOT output markdown code blocks

## Example Output:
[
  {{
    "food_name": "Pan-Seared White Fish",
    "portion_number": 150,
    "portion_unit": "gram",
    "total_calories": 180
  }},
  {{
    "food_name": "Whole Grain Bowl",
    "portion_number": 1,
    "portion_unit": "bowl",
    "total_calories": 250
  }},
  {{
    "food_name": "Olive Oil",
    "portion_number": 5,
    "portion_unit": "ml",
    "total_calories": 45
  }},
  {{
    "food_name": "Mixed Greens",
    "portion_number": 1,
    "portion_unit": "bowl",
    "total_calories": 25
  }}
]

## Task
Generate a single meal's base food items suitable for the user's profile.
The output will be expanded by a parser into Lite/Standard/Plus portions.
"""


def _to_food_item(item_dict: Dict[str, Any]) -> FoodItem:
    """Transform parser output to FoodItem format for DietRecommendation"""
    return FoodItem(
        food=item_dict.get("food_name", ""),
        portion=f"{item_dict.get('portion_number', '')}{item_dict.get('portion_unit', '')}",
        calories=int(round(item_dict.get("total_calories", 0))),
        protein=0.0,  # Placeholder - not tracked in new format
        carbs=0.0,    # Placeholder
        fat=0.0        # Placeholder
    )


def build_constraint_prompt(protein: str, carb: str, veg: str, excluded: List[str] = None) -> str:
    # prompt = "\n## Mandatory Ingredients (YOU MUST USE THESE)\n"
    # prompt += f"- Main Protein: {protein}\n"
    # prompt += f"- Carb Source: {carb}\n"
    # prompt += f"- Vegetable: {veg}\n"
    prompt = ""
    if excluded:
        prompt += f"\n## Excluded Ingredients (DO NOT USE)\n"
        prompt += f"- {', '.join(excluded)}\n"

    return prompt


# ================= Diet Agent =================

class DietAgent(BaseAgent, DietAgentMixin):
    """Agent for generating diet recommendation candidates"""

    def __init__(self):
        super().__init__()
        self.parser = DietPlanParser()

    def get_agent_name(self) -> str:
        return "diet"

    def get_input_type(self):
        return DietAgentInput

    def get_output_type(self):
        return DietRecommendation

    def generate(
        self,
        input_data: Dict[str, Any],
        num_variants: int = 3,
        meal_type: str = None,
        temperature: float = 0.7,
        top_p: float = 0.92,
        top_k: int = 50,
        user_preference: str = None
    ) -> List[DietRecommendation]:
        """
        Generate diet plan candidates using LLM + Parser pipeline.

        Flow:
        1. Calculate target calories from user profile
        2. Query KG for dietary knowledge (conditions, restrictions)
        3. For each meal type (or specified meal_type):
           - Call LLM to get base food items
           - Use Parser to expand to Lite/Standard/Plus
        4. Build candidates

        Args:
            input_data: User metadata, environment, requirements
            num_variants: Number of portion variants (1=Lite, 2=Lite+Standard, 3=Lite+Standard+Plus)
            meal_type: Specific meal type (breakfast/lunch/dinner/snacks) or None for all
            temperature: LLM temperature (0.0-1.0, default 0.7)
            user_preference: User's string preference (e.g., "I want a tuna sandwich with vegetable")

        Returns:
            List of DietRecommendation candidates
        """
        # Parse input
        input_obj = DietAgentInput(**input_data)

        user_meta = input_obj.user_metadata
        env = input_obj.environment
        requirement = input_obj.user_requirement

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

        # Query condition-based KG context
        if conditions:
            dietary_knowledge = self.query_dietary_knowledge(
                conditions, user_meta.get("dietary_restrictions", [])
            )
            kg_context = self._format_kg_context(dietary_knowledge)

        # Query entity-based KG context when user_preference is provided
        if user_preference:
            entity_knowledge = self.query_dietary_by_entity(user_preference)
            entity_context = self._format_entity_kg_context(entity_knowledge)
            kg_context += entity_context

        # Define meal types to generate
        if meal_type:
            meal_types = [meal_type]
        else:
            meal_types = ["breakfast", "lunch", "dinner", "snacks"]

        variant_names = ["Lite", "Standard", "Plus"][:num_variants]

        # [新增] 定义多样性池
        available_strategies = ["balanced", "protein_focus", "variety", "low_carb", "fiber_rich"]
        available_cuisines = ["Mediterranean", "Asian", "Western", "Fusion", "Local Home-style", "Simple & Quick"]
        used_strategies = set()  # 避免单次生成中策略过度重复
        used_combinations = set()  # 避免蛋白质+碳水组合重复

        # Collect base plans for each meal type
        meal_base_plans: Dict[str, Dict[str, Any]] = {}

        for mt in meal_types:
            # [改进] 随机选择策略，尽量不重复
            remaining_strategies = [s for s in available_strategies if s not in used_strategies]
            if not remaining_strategies:
                remaining_strategies = available_strategies

            strategy = random.choice(remaining_strategies)
            used_strategies.add(strategy)

            # [改进] 随机选择菜系/风格
            cuisine = random.choice(available_cuisines)

            # # [新增] 随机抽取核心食材 (Hero Ingredients)
            # protein = random.choice(PROTEIN_SOURCES)
            # carb = random.choice(CARB_SOURCES)
            # veg = random.choice(VEG_SOURCES)

            # # [新增] 避免重复组合
            # combo_key = f"{protein}-{carb}"
            # max_attempts = 3
            # attempts = 0
            # while combo_key in used_combinations and attempts < max_attempts:
            #     protein = random.choice(PROTEIN_SOURCES)
            #     carb = random.choice(CARB_SOURCES)
            #     combo_key = f"{protein}-{carb}"
            #     attempts += 1
            # used_combinations.add(combo_key)

            # [新增] 随机禁用"无聊"食材 (50% 概率)
            excluded = []
            if random.random() > 0.5:
                excluded = random.sample(COMMON_BORING_FOODS, k=random.randint(1, 2))

            # [新增] 构建约束 Prompt
            # constraint_prompt = build_constraint_prompt(protein, carb, veg, excluded)

            # print(f"[DEBUG] {mt}: protein={protein}, carb={carb}, veg={veg}, excluded={excluded}")

            base_items = self._generate_base_plan(
                user_meta=user_meta,
                environment=env,
                requirement=requirement,
                target_calories=target_calories,
                meal_type=mt,
                kg_context=kg_context,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                strategy=strategy,
                cuisine=cuisine,
                # constraint_prompt=constraint_prompt,
                constraint_prompt="",
                user_preference=user_preference
            )
            if base_items:
                meal_base_plans[mt] = {
                    "items": base_items,
                    "strategy": strategy,
                    "cuisine": cuisine,
                    "excluded": excluded
                }

        if not meal_base_plans:
            print("[WARN] No base plans generated for any meal type")
            return []

        # Expand each meal to variants
        expanded_meals: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for meal_type, plan_info in meal_base_plans.items():
            expanded_meals[meal_type] = self.parser.expand_plan(plan_info["items"], variant_names)

        # Build candidates: one DietRecommendation per meal with variants
        # Output structure: [breakfast_lite, breakfast_std, breakfast_plus, lunch_lite, ...]
        candidates = []
        candidate_id = 1

        # Calorie targets per meal type
        meal_targets = {
            "breakfast": int(target_calories * 0.25),
            "lunch": int(target_calories * 0.35),
            "dinner": int(target_calories * 0.30),
            "snacks": int(target_calories * 0.10)
        }

        for meal_type in meal_types:
            if meal_type not in expanded_meals:
                continue

            # Get strategy and cuisine for this meal
            plan_info = meal_base_plans.get(meal_type, {})
            strategy = plan_info.get("strategy", "balanced")
            cuisine = plan_info.get("cuisine", "General")

            meal_variants = expanded_meals[meal_type]
            target = meal_targets.get(meal_type, int(target_calories * 0.25))

            for variant_name in variant_names:
                meal_items = meal_variants.get(variant_name, [])
                if not meal_items:
                    continue

                # Transform to FoodItem format
                food_items = [_to_food_item(item) for item in meal_items]
                total_cal = sum(item.calories for item in food_items)

                # Calculate deviation
                deviation = round(((total_cal - target) / target) * 100, 1)

                # Build safety notes
                safety_notes = [f"Meal: {meal_type}", f"Variant: {variant_name}"]
                safety_notes.append(f"Style: {cuisine}, Strategy: {strategy}")
                # [新增] 记录食材约束
                excluded = plan_info.get("excluded", [])
                if excluded:
                    safety_notes.append(f"Excluded: {', '.join(excluded)}")
                if abs(deviation) > 10:
                    safety_notes.append(f"Calorie deviation: {deviation}%")

                candidate = DietRecommendation(
                    id=candidate_id,
                    meal_type=meal_type,
                    variant=variant_name,
                    items=food_items,
                    total_calories=int(total_cal),
                    target_calories=target,
                    calories_deviation=deviation,
                    safety_notes=safety_notes
                )
                candidates.append(candidate)
                candidate_id += 1

        # Sort by deviation
        candidates.sort(key=lambda x: (x.meal_type, abs(x.calories_deviation)))

        return candidates

    def _generate_base_plan(
        self,
        user_meta: Dict[str, Any],
        environment: Dict[str, Any],
        requirement: Dict[str, Any],
        target_calories: int,
        meal_type: str,
        kg_context: str = "",
        temperature: float = 0.85,  # [改进] 提高温度增加随机性
        top_p: float = 0.92,
        top_k: int = 50,
        strategy: str = "balanced",
        cuisine: str = "General",
        constraint_prompt: str = "",
        user_preference: str = None
    ) -> Optional[List[BaseFoodItem]]:
        """Generate base food items for a single meal type with diversity injection"""

        strategy_guidance = {
            "balanced": "Focus on balanced nutrition across all macros.",
            "protein_focus": "Emphasize high-protein foods for muscle maintenance.",
            "variety": "Include diverse food types and colors.",
            "low_carb": "Reduce carbohydrate intake slightly, focus on quality fats and proteins.",
            "fiber_rich": "Prioritize high-fiber vegetables and whole grains."
        }

        user_prompt = self._build_diet_prompt(
            user_meta=user_meta,
            environment=environment,
            requirement=requirement,
            target_calories=target_calories,
            meal_type=meal_type,
            kg_context=kg_context,
            user_preference=user_preference
        )

        # [改进] 构建更具独特性的 Prompt
        full_prompt = user_prompt + f"\n\n### Optimization Strategy: {strategy.upper()}\n{strategy_guidance.get(strategy, '')}"
        full_prompt += f"\n\n### Culinary Style: {cuisine}\nPLEASE strictly follow this style. Use ingredients and cooking methods typical for {cuisine} cuisine."
        full_prompt += constraint_prompt  # [新增] 注入强制食材约束

        response = self._call_llm(
            system_prompt=DIET_GENERATION_SYSTEM_PROMPT,
            user_prompt=full_prompt,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k
        )

        if not response or response == {}:
            print(f"[WARN] LLM returned empty for {meal_type}")
            return None

        try:
            data = parse_json_response(response)
        except json.JSONDecodeError as e:
            print(f"[WARN] Invalid JSON for {meal_type}: {e}")
            return None

        # Parse to BaseFoodItem list
        if isinstance(data, list):
            items = []
            for i, item_data in enumerate(data):
                try:
                    item = BaseFoodItem(**item_data)
                    items.append(item)
                except Exception as e:
                    print(f"[WARN] Failed to parse item {i}: {e}")
            return items if items else None
        else:
            print(f"[WARN] Expected list, got {type(data)}")
            return None

    def _get_activity_factor(self, fitness_level: str) -> float:
        """Get activity factor from fitness level"""
        factors = {
            "sedentary": 1.2,
            "beginner": 1.375,
            "intermediate": 1.55,
            "advanced": 1.725
        }
        return factors.get(fitness_level, 1.2)

    def _format_kg_context(self, knowledge: List) -> str:
        """Format KG knowledge for prompt"""
        if not knowledge:
            return ""

        parts = []

        # set maximum input lengths = 20
        maximum_inputs = 20
        if len(knowledge)>maximum_inputs:
            random.shuffle(knowledge)
            knowledge = knowledge[:maximum_inputs]
        
        for item in knowledge:
            entity_name = item.get('entity', "name")
            rel = item.get('rel', "relation")
            tail = item.get('tail', "name")
            condition = item.get('condition', "condition")

            part = "{} {} {} under condition: {}".format(entity_name, rel, tail, condition)
            parts.append(part)

        return "## KG Guidelines\n" + "\n".join(parts) + "\n"

    def _build_diet_prompt(
        self,
        user_meta: Dict[str, Any],
        environment: Dict[str, Any],
        requirement: Dict[str, Any],
        target_calories: int,
        meal_type: str = "breakfast",
        kg_context: str = "",
        user_preference: str = None
    ) -> str:
        """Build the user prompt for a specific meal type generation"""
        conditions = user_meta.get("medical_conditions", [])
        restrictions = user_meta.get("dietary_restrictions", [])

        # Calorie targets per meal
        meal_targets = {
            "breakfast": int(target_calories * 0.25),
            "lunch": int(target_calories * 0.35),
            "dinner": int(target_calories * 0.30),
            "snacks": int(target_calories * 0.10)
        }
        target = meal_targets.get(meal_type, int(target_calories * 0.25))

        # Build user profile section
        profile_parts = [
            f"Age: {user_meta.get('age', 30)}",
            f"Gender: {user_meta.get('gender', 'male')}",
        ]
        if conditions:
            profile_parts.append(f"Conditions: {', '.join(conditions)}")
        if restrictions:
            profile_parts.append(f"Restrictions: {', '.join(restrictions)}")

        prompt = f"""## Profile
{chr(10).join(profile_parts)}

## Target
Goal: {requirement.get('goal', 'maintenance')}
{meal_type.capitalize()}: {target} kcal (max)
{chr(10)}{kg_context}"""

        # Add user preference if provided
        if user_preference:
            prompt += f"\n## User Preference\n{user_preference}\n"

        prompt += f"""## Output Format
JSON list of foods. Each item:
- food_name: name
- portion_number: number
- portion_unit: gram/ml/piece/slice/cup/bowl/spoon
- calories_per_unit: calories per single unit

## Example (~{target} kcal)
[
  {{"food_name": "X", "portion_number": 100, "portion_unit": "gram", "calories_per_unit": 3.5}},
  {{"food_name": "Y", "portion_number": 2, "portion_unit": "piece", "calories_per_unit": 78}}
]

## Task
Generate {meal_type} foods totaling ~{target} kcal. List only JSON."""

        return prompt


# ================= Convenience Functions =================

def generate_diet_candidates(
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {},
    user_requirement: Dict[str, Any] = {},
    num_variants: int = 3,
    meal_type: str = None,
    temperature: float = 0.7,
    top_p: float = 0.92,
    top_k: int = 50,
    user_preference: str = None
) -> List[DietRecommendation]:
    """
    Convenience function to generate diet candidates.

    Args:
        user_metadata: User physiological data
        environment: Environmental context
        user_requirement: User goals
        num_variants: Number of portion variants (1=Lite, 2=Lite+Standard, 3=Lite+Standard+Plus)
        meal_type: Specific meal type (breakfast/lunch/dinner/snacks) or None for all
        temperature: LLM temperature (0.0-1.0, default 0.7)
        top_p: LLM top_p for nucleus sampling (0.0-1.0, default 0.92)
        top_k: LLM top_k for top-k sampling (default 50)
        user_preference: User's string preference (e.g., "I want a tuna sandwich with vegetable")

    Returns:
        List of DietRecommendation objects
    """
    agent = DietAgent()
    input_data = {
        "user_metadata": user_metadata,
        "environment": environment,
        "user_requirement": user_requirement,
    }
    return agent.generate(input_data, num_variants, meal_type, temperature, top_p, top_k, user_preference)


if __name__ == "__main__":
    # Test the generator
    test_input = {
        "user_metadata": {
            "age": 35,
            "gender": "male",
            "height_cm": 175,
            "weight_kg": 70,
            "medical_conditions": ["diabetes"],
            "dietary_restrictions": ["low_sodium"],
            "fitness_level": "intermediate"
        },
        "environment": {
            "weather": {"condition": "clear", "temperature_c": 25},
            "time_context": {"season": "summer"}
        },
        "user_requirement": {
            "goal": "weight_loss"
        },
        "num_variants": 3
    }

    candidates = generate_diet_candidates(**test_input)
    print(f"Generated {len(candidates)} diet candidates")
    for c in candidates:
        print(f"\n[ID:{c.id}] {c.meal_type.upper()} - {c.variant}")
        print(f"  Target: {c.target_calories} kcal | Actual: {c.total_calories} kcal | Deviation: {c.calories_deviation}%")
        for item in c.items:
            print(f"  - {item.food}: {item.portion} ({item.calories} kcal)")

