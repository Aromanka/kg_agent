"""
Diet Candidate Generator
Generates personalized meal plan candidates based on user metadata and knowledge graph.

Refactored to use BaseAgent architecture.
"""
import json
import re
from typing import List, Dict, Any, Optional
from agents.base import BaseAgent, DietAgentMixin
from agents.diet.models import (
    FoodItem, MealPlanItem, MacroNutrients,
    DietRecommendation, DietCandidatesResponse, DietAgentInput
)
from core.llm.utils import parse_json_response


# ================= System Prompt =================

DIET_GENERATION_SYSTEM_PROMPT = """You are a professional nutritionist. Generate personalized meal plans based on user health data.

## Daily Calorie Distribution
- Breakfast: 25% of daily calories
- Lunch: 35% of daily calories
- Dinner: 30% of daily calories
- Snacks: 10% of daily calories

## Macro Nutrient Ratios (healthy adults)
- Protein: 15-25% of calories
- Carbs: 45-65% of calories
- Fat: 20-35% of calories

## Special Conditions
- Diabetes: Low GI foods, control carbs
- Hypertension: Low sodium (<2000mg/day)
- Hyperlipidemia: Reduce saturated fat, increase fiber
- Weight loss: 300-500 kcal deficit
- Muscle gain: High protein (1.6-2.2g/kg)

## Output Format
Return valid JSON object directly. Do NOT wrap in extra keys like "diet_plan" or "candidates".
The JSON must contain these fields:
- id: integer
- meal_plan: object with keys "breakfast", "lunch", "dinner", "snacks"
- total_calories: integer
- calories_deviation: float
- macro_nutrients: object with "protein", "carbs", "fat", "protein_ratio", "carbs_ratio", "fat_ratio"
- safety_notes: array of strings
"""


# ================= Diet Agent =================

class DietAgent(BaseAgent, DietAgentMixin):
    """Agent for generating diet recommendation candidates"""

    def get_agent_name(self) -> str:
        return "diet"

    def get_input_type(self):
        return DietAgentInput

    def get_output_type(self):
        return DietRecommendation

    def generate(
        self,
        input_data: Dict[str, Any],
        num_candidates: int = 3
    ) -> List[DietRecommendation]:
        """Generate diet plan candidates"""
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

        # Build user prompt
        user_prompt = self._build_diet_prompt(
            user_meta=user_meta,
            environment=env,
            requirement=requirement,
            target_calories=target_calories,
            kg_context=kg_context
        )

        # Generate candidates
        candidates = []
        for i in range(num_candidates):
            strategy = ["balanced", "protein_focus", "variety"][i % 3] if num_candidates > 1 else "balanced"

            candidate = self._generate_single_candidate(
                user_prompt=user_prompt,
                candidate_id=i + 1,
                strategy=strategy
            )
            if candidate:
                candidates.append(candidate)

        # Sort by calorie deviation
        candidates.sort(key=lambda x: abs(x.calories_deviation))

        return candidates

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
        kg_context: str = ""
    ) -> str:
        """Build the user prompt for diet generation"""
        conditions = user_meta.get("medical_conditions", [])
        restrictions = user_meta.get("dietary_restrictions", [])
        season = environment.get("time_context", {}).get("season", "any")

        prompt = f"""## User Profile

**Age**: {user_meta.get('age', 30)}
**Gender**: {user_meta.get('gender', 'male')}
**Height**: {user_meta.get('height_cm', 170)}cm
**Weight**: {user_meta.get('weight_kg', 70)}kg
**Fitness Level**: {user_meta.get('fitness_level', 'beginner')}
**Medical Conditions**: {', '.join(conditions) if conditions else 'None'}
**Dietary Restrictions**: {', '.join(restrictions) if restrictions else 'None'}

## Goal
**Primary Goal**: {requirement.get('goal', 'maintenance')}
**Target Calories**: {target_calories} kcal

## Environment
**Season**: {season}

## Calorie Distribution
- Breakfast: {int(target_calories * 0.25)} kcal (25%)
- Lunch: {int(target_calories * 0.35)} kcal (35%)
- Dinner: {int(target_calories * 0.30)} kcal (30%)
- Snacks: {int(target_calories * 0.10)} kcal (10%)

{kg_context}

## Task
Generate a single diet plan candidate. Return ONLY the JSON object, NO markdown code blocks, NO extra wrapper keys.
Each food item in meal_plan MUST have: "food", "portion", "calories", "protein", "carbs", "fat".

Example format:
{{
  "id": 1,
  "meal_plan": {{
    "breakfast": [
      {{
        "food": "Oatmeal with Berries",
        "portion": "1 bowl (200g)",
        "calories": 300,
        "protein": 10.5,
        "carbs": 50.0,
        "fat": 6.0
      }}
    ],
    "lunch": [
      {{
        "food": "Grilled Chicken Breast",
        "portion": "150g",
        "calories": 250,
        "protein": 45.0,
        "carbs": 0.0,
        "fat": 5.0
      }}
    ],
    "dinner": [
      {{
        "food": "Steamed Fish with Vegetables",
        "portion": "200g fish + 150g vegetables",
        "calories": 350,
        "protein": 40.0,
        "carbs": 15.0,
        "fat": 12.0
      }}
    ],
    "snacks": [
      {{
        "food": "Mixed Nuts",
        "portion": "30g",
        "calories": 180,
        "protein": 6.0,
        "carbs": 8.0,
        "fat": 16.0
      }}
    ]
  }},
  "total_calories": 1800,
  "calories_deviation": -5.5,
  "macro_nutrients": {{
    "protein": 90,
    "carbs": 200,
    "fat": 60,
    "protein_ratio": 0.20,
    "carbs_ratio": 0.45,
    "fat_ratio": 0.30
  }},
  "safety_notes": []
}}"""

        return prompt

    def _generate_single_candidate(
        self,
        user_prompt: str,
        candidate_id: int,
        strategy: str = "balanced"
    ) -> Optional[DietRecommendation]:
        """Generate a single diet candidate"""
        strategy_guidance = {
            "balanced": "Focus on balanced nutrition across all macros.",
            "protein_focus": "Emphasize high-protein foods for muscle maintenance.",
            "variety": "Include diverse food types and colors."
        }

        full_prompt = user_prompt + f"\n\n### Strategy: {strategy.upper()}\n{strategy_guidance.get(strategy, '')}"

        # try:
        response = self._call_llm(
            system_prompt=DIET_GENERATION_SYSTEM_PROMPT,
            user_prompt=full_prompt,
            temperature=0.7
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

        return DietRecommendation(**plan_data)

        # except Exception as e:
        #     print(f"Error generating diet candidate {candidate_id}: {e}")
        #     return None


# ================= Convenience Functions =================

def generate_diet_candidates(
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {},
    user_requirement: Dict[str, Any] = {},
    num_candidates: int = 3
) -> List[DietRecommendation]:
    """
    Convenience function to generate diet candidates.

    Args:
        user_metadata: User physiological data
        environment: Environmental context
        user_requirement: User goals
        num_candidates: Number of candidates

    Returns:
        List of DietRecommendation objects
    """
    agent = DietAgent()
    input_data = {
        "user_metadata": user_metadata,
        "environment": environment,
        "user_requirement": user_requirement,
        "num_candidates": num_candidates
    }
    return agent.generate(input_data, num_candidates)


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
        "num_candidates": 2
    }

    candidates = generate_diet_candidates(**test_input)
    print(f"Generated {len(candidates)} diet candidates")
    for c in candidates:
        print(f"- ID: {c.id}, Calories: {c.total_calories}, Deviation: {c.calories_deviation}%")

