"""
Diet Candidate Generator
Generates personalized meal plan candidates based on user metadata and knowledge graph.

Architecture: LLM generates base plan → Parser expands to Lite/Standard/Plus variants.
"""
import json
import re
from typing import List, Dict, Any, Optional
from agents.base import BaseAgent, DietAgentMixin
from agents.diet.models import (
    FoodItem, MealPlanItem, MacroNutrients,
    DietRecommendation, DietCandidatesResponse, DietAgentInput,
    BaseFoodItem
)
from agents.diet.parser import DietPlanParser
from core.llm.utils import parse_json_response


# ================= System Prompt =================

# Allowed units for portion (must match parser rules)
UNIT_LIST_STR = '["gram", "ml", "piece", "slice", "cup", "bowl", "spoon"]'

DIET_GENERATION_SYSTEM_PROMPT = f"""You are a professional nutritionist. Generate BASE meal plans with standardized portions.

## Output Format
Output MUST be a valid JSON list of objects. Each object is a food item with these fields:
- "food_name": string (name of the food)
- "portion_number": number (numeric quantity, e.g., 100, 1.5, 2)
- "portion_unit": string (MUST be one of: {UNIT_LIST_STR})
- "calories_per_unit": number (calories for ONE unit, e.g., per gram or per piece)

## Rules
1. Use ONLY the allowed units listed above
2. Provide accurate calories_per_unit based on nutritional data
3. Output food items for ONE meal type as a JSON LIST
4. Do NOT wrap in extra keys like "meal_plan" or "items"
5. Do NOT output markdown code blocks

## Example Output (breakfast):
[
  {{
    "food_name": "Oatmeal",
    "portion_number": 50,
    "portion_unit": "gram",
    "calories_per_unit": 3.5
  }},
  {{
    "food_name": "Boiled Egg",
    "portion_number": 2,
    "portion_unit": "piece",
    "calories_per_unit": 78
  }},
  {{
    "food_name": "Banana",
    "portion_number": 1,
    "portion_unit": "piece",
    "calories_per_unit": 105
  }}
]

## Task
Generate a single meal's base food items suitable for the user's profile.
The output will be expanded by a parser into Lite/Standard/Plus portions.
"""


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
        num_variants: int = 3
    ) -> List[DietRecommendation]:
        """
        Generate diet plan candidates using LLM + Parser pipeline.

        Flow:
        1. Calculate target calories from user profile
        2. Query KG for dietary knowledge (conditions, restrictions)
        3. For each meal type (breakfast/lunch/dinner/snacks):
           - Call LLM once to get base food items
           - Use Parser to expand to Lite/Standard/Plus
        4. Combine all meal types into complete day plans

        Args:
            input_data: User metadata, environment, requirements
            num_variants: Number of portion variants (1=Lite, 2=Lite+Standard, 3=Lite+Standard+Plus)

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
        if conditions:
            dietary_knowledge = self.query_dietary_knowledge(
                conditions, user_meta.get("dietary_restrictions", [])
            )
            kg_context = self._format_kg_context(dietary_knowledge)

        # Define meal types to generate
        meal_types = ["breakfast", "lunch", "dinner", "snacks"]
        variant_names = ["Lite", "Standard", "Plus"][:num_variants]

        # Collect base plans for each meal type
        meal_base_plans: Dict[str, List[BaseFoodItem]] = {}

        for meal_type in meal_types:
            base_items = self._generate_base_plan(
                user_meta=user_meta,
                environment=env,
                requirement=requirement,
                target_calories=target_calories,
                meal_type=meal_type,
                kg_context=kg_context
            )
            if base_items:
                meal_base_plans[meal_type] = base_items

        if not meal_base_plans:
            print("[WARN] No base plans generated for any meal type")
            return []

        # Expand each meal to variants
        expanded_meals: Dict[str, Dict[str, List[Dict]]] = {}
        for meal_type, base_items in meal_base_plans.items():
            expanded_meals[meal_type] = self.parser.expand_plan(base_items, variant_names)

        # Build complete day plans for each variant
        candidates = []
        for variant_idx, variant_name in enumerate(variant_names):
            full_day_plan: Dict[str, List[Dict]] = {}
            total_cal = 0

            for meal_type in meal_types:
                if meal_type in expanded_meals:
                    meal_items = expanded_meals[meal_type].get(variant_name, [])
                    full_day_plan[meal_type] = meal_items
                    meal_cal = sum(item.get("total_calories", 0) for item in meal_items)
                    total_cal += meal_cal

            # Calculate deviation from target
            deviation = round(((total_cal - target_calories) / target_calories) * 100, 1)

            # Build safety notes
            safety_notes = [f"Variant: {variant_name}"]
            if abs(deviation) > 10:
                safety_notes.append(f"Calorie deviation: {deviation}%")

            candidate = DietRecommendation(
                id=variant_idx + 1,
                meal_plan=full_day_plan,
                total_calories=int(total_cal),
                calories_deviation=deviation,
                macro_nutrients=MacroNutrients(
                    protein=0, carbs=0, fat=0,
                    protein_ratio=0.2, carbs_ratio=0.5, fat_ratio=0.3
                ),
                safety_notes=safety_notes
            )
            candidates.append(candidate)

        # Sort by deviation
        candidates.sort(key=lambda x: abs(x.calories_deviation))

        return candidates

    def _generate_base_plan(
        self,
        user_meta: Dict[str, Any],
        environment: Dict[str, Any],
        requirement: Dict[str, Any],
        target_calories: int,
        meal_type: str,
        kg_context: str = ""
    ) -> Optional[List[BaseFoodItem]]:
        """Generate base food items for a single meal type"""
        user_prompt = self._build_diet_prompt(
            user_meta=user_meta,
            environment=environment,
            requirement=requirement,
            target_calories=target_calories,
            meal_type=meal_type,
            kg_context=kg_context
        )

        response = self._call_llm(
            system_prompt=DIET_GENERATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.7
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

    def _format_kg_context(self, knowledge: Dict) -> str:
        """Format KG knowledge for prompt"""
        context = "\n## Knowledge Graph Context\n"

        if knowledge.get("recommended_foods"):
            foods = [f.get("food", "") for f in knowledge["recommended_foods"]]
            context += f"- Recommended foods: {', '.join(set(foods))}\n"

        if knowledge.get("restricted_foods"):
            restrictions = [r.get("restriction", "") for r in knowledge["restricted_foods"]]
            context += f"- Restrictions: {', '.join(set(restrictions))}\n"

        if knowledge.get("nutrient_advice"):
            for advice in knowledge["nutrient_advice"][:3]:
                context += f"- {advice.get('nutrient', '')}: {advice.get('advice', '')}\n"

        return context

    def _build_diet_prompt(
        self,
        user_meta: Dict[str, Any],
        environment: Dict[str, Any],
        requirement: Dict[str, Any],
        target_calories: int,
        meal_type: str = "breakfast",
        kg_context: str = ""
    ) -> str:
        """Build the user prompt for a specific meal type generation"""
        conditions = user_meta.get("medical_conditions", [])
        restrictions = user_meta.get("dietary_restrictions", [])
        season = environment.get("time_context", {}).get("season", "any")

        # Calorie targets per meal
        meal_calories = {
            "breakfast": int(target_calories * 0.25),
            "lunch": int(target_calories * 0.35),
            "dinner": int(target_calories * 0.30),
            "snacks": int(target_calories * 0.10)
        }
        target = meal_calories.get(meal_type, int(target_calories * 0.25))

        prompt = f"""## User Profile

**Age**: {user_meta.get('age', 30)}
**Gender**: {user_meta.get('gender', 'male')}
**Medical Conditions**: {', '.join(conditions) if conditions else 'None'}
**Dietary Restrictions**: {', '.join(restrictions) if restrictions else 'None'}

## Goal
**Primary Goal**: {requirement.get('goal', 'maintenance')}
**Target Calories**: {target_calories} kcal total

## This Meal: {meal_type.upper()}
**Target for {meal_type}: {target} kcal**

{kg_context}

## Task
Generate food items for {meal_type} totaling approximately {target} kcal.
Return ONLY a JSON list of food items with standardized portions.

Each item must have:
- food_name: name of the food
- portion_number: numeric quantity
- portion_unit: gram, ml, piece, slice, cup, bowl, or spoon
- calories_per_unit: calories for ONE unit

Example (breakfast ~450 kcal):
[
  {{
    "food_name": "Oatmeal",
    "portion_number": 80,
    "portion_unit": "gram",
    "calories_per_unit": 3.5
  }},
  {{
    "food_name": "Boiled Egg",
    "portion_number": 2,
    "portion_unit": "piece",
    "calories_per_unit": 78
  }}
]"""

        return prompt


# ================= Convenience Functions =================

def generate_diet_candidates(
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {},
    user_requirement: Dict[str, Any] = {},
    num_variants: int = 3
) -> List[DietRecommendation]:
    """
    Convenience function to generate diet candidates.

    Args:
        user_metadata: User physiological data
        environment: Environmental context
        user_requirement: User goals
        num_variants: Number of portion variants (1=Lite, 2=Lite+Standard, 3=Lite+Standard+Plus)

    Returns:
        List of DietRecommendation objects
    """
    agent = DietAgent()
    input_data = {
        "user_metadata": user_metadata,
        "environment": environment,
        "user_requirement": user_requirement,
    }
    return agent.generate(input_data, num_variants)


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
        print(f"- ID: {c.id}, Calories: {c.total_calories}, Deviation: {c.calories_deviation}%")

