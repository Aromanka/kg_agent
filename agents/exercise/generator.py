"""
Exercise Candidate Generator
Generates personalized exercise plan candidates based on user metadata and knowledge graph.
"""
import json
import os
from typing import List, Dict, Any, Optional
from agents.base import BaseAgent, DietAgentMixin, ExerciseAgentMixin
from agents.exercise.models import (
    ExerciseType, IntensityLevel, TimeOfDay,
    ExerciseItem, ExerciseSession, ExercisePlan,
    ExerciseCandidatesResponse, ExerciseAgentInput
)
from core.llm import get_llm
from core.neo4j import get_kg_query


# ================= System Prompts =================

EXERCISE_GENERATION_SYSTEM_PROMPT = """You are a professional exercise prescription AI. Your task is to generate personalized exercise plans based on user health data.

## Guidelines

### Exercise Types
- CARDIO: Running, swimming, cycling, rowing, jumping rope
- STRENGTH: Weight lifting, bodyweight exercises, resistance bands
- FLEXIBILITY: Stretching, yoga, Pilates
- BALANCE: Balance training, tai chi
- HIIT: High-intensity interval training

### Intensity Levels
- LOW: Gentle movement, warm-up level (RPE 1-3)
- MODERATE: Sustainable effort, conversation possible (RPE 4-6)
- HIGH: Challenging, breathing heavily (RPE 7-8)
- VERY_HIGH: Maximum effort, short bursts only (RPE 9-10)

### Calories per Minute (MET-based estimates)
- Walking (moderate): 4-5 kcal/min
- Running: 10-12 kcal/min
- Swimming: 8-10 kcal/min
- Cycling: 6-10 kcal/min
- Strength training: 5-8 kcal/min
- Yoga: 2-4 kcal/min
- HIIT: 12-15 kcal/min

### Safety Rules
1. For beginners: Start with LOW intensity, 15-20 min sessions
2. For intermediate: MODERATE intensity, 30-45 min sessions
3. For advanced: HIGH intensity, 45-60 min sessions
4. Cardiac conditions: Avoid HIGH/VERY_HIGH intensity
5. Joint problems: Prioritize LOW-impact exercises (swimming, cycling)
6. Diabetic users: Avoid vigorous exercise during hypoglycemia risk periods
7. Always include warm-up and cool-down

## Output Format
Return a valid JSON object matching the provided schema. Each exercise must include:
- Clear name and type
- Appropriate duration for fitness level
- Calorie burn estimate
- Safety considerations specific to user's conditions
"""


# ================= Helper Functions =================

def calculate_target_calories_burned(
    weight_kg: float,
    goal: str = "maintenance",
    activity_factor: float = 1.2
) -> int:
    """Calculate target daily calories to burn based on goal"""
    # Basal metabolic rate (simplified)
    bmr = 25 * weight_kg

    # Target calorie burn from exercise
    goal_targets = {
        "weight_loss": 300,
        "muscle_building": 200,
        "cardio_improvement": 400,
        "flexibility": 100,
        "maintenance": 150
    }

    return goal_targets.get(goal, 200)


def get_exercise_for_condition(
    condition: str,
    fitness_level: str = "beginner"
) -> Dict[str, Any]:
    """Get exercise recommendations/restrictions for a medical condition"""
    condition_exercises = {
        "diabetes": {
            "recommended": ["walking", "swimming", "cycling", "light_strength"],
            "avoid": ["high_intensity_hiit", "extreme_endurance"],
            "notes": ["Avoid exercise during peak insulin activity", "Check blood sugar before/after"]
        },
        "hypertension": {
            "recommended": ["walking", "swimming", "yoga", "light_cycling"],
            "avoid": ["heavy_weightlifting", "high_intensity_hiit", "valsalva_maneuver"],
            "notes": ["Monitor blood pressure", "Avoid isometric exercises"]
        },
        "heart_disease": {
            "recommended": ["light_walking", "slow_cycling", "water_exercise"],
            "avoid": ["running", "hiit", "heavy_lifting", "competitive_sports"],
            "notes": ["Medical clearance required", "Keep intensity low", "Stop if chest pain"]
        },
        "obesity": {
            "recommended": ["walking", "water_aerobics", "recumbent_bike", "elliptical"],
            "avoid": ["running", "jumping", "high_impact_activities"],
            "notes": ["Start slow, progress gradually", "Focus on low-impact options"]
        },
        "arthritis": {
            "recommended": ["swimming", "water_exercise", "cycling", "yoga"],
            "avoid": ["running", "high_impact_jumping", "heavy_lifting"],
            "notes": ["Range of motion exercises preferred", "Avoid high-impact"]
        },
        "back_pain": {
            "recommended": ["swimming", "walking", "yoga", "pilates"],
            "avoid": ["heavy_squat", "deadlift", "high_impact_jumping"],
            "notes": ["Core strengthening recommended", "Avoid hyperextension"]
        }
    }

    return condition_exercises.get(condition.lower(), {
        "recommended": ["walking", "cycling", "swimming"],
        "avoid": [],
        "notes": ["Consult physician before starting"]
    })


# ================= Exercise Agent =================

class ExerciseAgent(BaseAgent, ExerciseAgentMixin):
    """Agent for generating exercise plan candidates"""

    def get_agent_name(self) -> str:
        return "exercise"

    def get_input_type(self):
        return ExerciseAgentInput

    def get_output_type(self):
        return ExercisePlan

    def generate(
        self,
        input_data: Dict[str, Any],
        num_candidates: int = 3
    ) -> List[ExercisePlan]:
        """Generate exercise plan candidates"""
        # Parse input
        input_obj = ExerciseAgentInput(**input_data)

        user_meta = input_obj.user_metadata
        env = input_obj.environment
        requirement = input_obj.user_requirement

        # Extract key parameters
        conditions = user_meta.get("medical_conditions", [])
        fitness_level = user_meta.get("fitness_level", "beginner")
        weight = user_meta.get("weight_kg", 70)
        goal = requirement.get("goal", "maintenance")
        preferred_intensity = requirement.get("intensity", "moderate")

        # Calculate target calories
        target_calories = calculate_target_calories_burned(weight, goal)

        # Get knowledge graph context
        kg_context = ""
        if conditions:
            for condition in conditions:
                cond_info = get_exercise_for_condition(condition, fitness_level)
                kg_context += f"\n### Condition: {condition}\n"
                kg_context += f"- Recommended: {cond_info['recommended']}\n"
                kg_context += f"- Avoid: {cond_info['avoid']}\n"
                kg_context += f"- Notes: {cond_info['notes']}\n"

        # Get environment context
        weather = env.get("weather", {})
        season = env.get("time_context", {}).get("season", "any")

        # Build user prompt
        user_prompt = self._build_exercise_prompt(
            user_meta=user_meta,
            environment=env,
            requirement=requirement,
            kg_context=kg_context,
            target_calories=target_calories
        )

        # Generate candidates using LLM
        candidates = []
        for i in range(num_candidates):
            # Vary sampling strategy for diversity
            strategy = ["balanced", "protein_focus", "variety"][i % 3] if num_candidates > 1 else "balanced"

            candidate = self._generate_single_candidate(
                user_prompt=user_prompt,
                candidate_id=i + 1,
                fitness_level=fitness_level,
                weight=weight,
                strategy=strategy
            )
            if candidate:
                candidates.append(candidate)

        return candidates

    def _build_exercise_prompt(
        self,
        user_meta: Dict[str, Any],
        environment: Dict[str, Any],
        requirement: Dict[str, Any],
        kg_context: str,
        target_calories: int
    ) -> str:
        """Build the user prompt for exercise generation"""
        conditions = user_meta.get("medical_conditions", [])
        fitness_level = user_meta.get("fitness_level", "beginner")
        weight = user_meta.get("weight_kg", 70)
        goal = requirement.get("goal", "maintenance")

        prompt = f"""## User Profile

**Age**: {user_meta.get('age', 30)}
**Gender**: {user_meta.get('gender', 'male')}
**Weight**: {weight}kg
**Fitness Level**: {fitness_level}
**Medical Conditions**: {', '.join(conditions) if conditions else 'None'}

## Goal
**Primary Goal**: {goal}
**Preferred Intensity**: {requirement.get('intensity', 'moderate')}
**Target Daily Calories Burn**: {target_calories} kcal

## Environment Context
**Weather**: {environment.get('weather', {})}
**Season**: {environment.get('time_context', {}).get('season', 'any')}

## Knowledge Graph Context
{kg_context}

## Task
Generate {requirement.get('num_candidates', 3)} different exercise plan candidates.

For each candidate:
1. Create 2-3 sessions (morning/afternoon/evening)
2. Each session should have 2-4 exercises
3. Total daily calories should be close to {target_calories}
4. Include warm-up and cool-down in appropriate sessions
5. Consider the user's medical conditions and fitness level
6. Provide progression plan for 4-week period

Return JSON array of exercise plans matching the schema."""

        return prompt

    def _generate_single_candidate(
        self,
        user_prompt: str,
        candidate_id: int,
        fitness_level: str,
        weight: float,
        strategy: str = "balanced"
    ) -> Optional[ExercisePlan]:
        """Generate a single exercise plan candidate"""
        # Add strategy-specific guidance
        strategy_guidance = {
            "balanced": "Focus on mix of cardio, strength, and flexibility.",
            "protein_focus": "Emphasize strength training with progressive overload.",
            "variety": "Include diverse exercises to prevent boredom and plateaus."
        }

        full_prompt = user_prompt + f"\n\n### Strategy: {strategy.upper()}\n{strategy_guidance.get(strategy, '')}"

        # Call LLM
        try:
            response = self._call_llm(
                system_prompt=EXERCISE_GENERATION_SYSTEM_PROMPT,
                user_prompt=full_prompt,
                temperature=0.8
            )

            # Parse JSON response
            if isinstance(response, str):
                import json
                data = json.loads(response)
            else:
                data = response

            # Handle different response formats
            if isinstance(data, list):
                plan_data = data[0] if data else {}
            elif isinstance(data, dict):
                plan_data = data
            else:
                return None

            # Ensure ID is set
            if "id" not in plan_data:
                plan_data["id"] = candidate_id

            # Create ExercisePlan object
            return ExercisePlan(**plan_data)

        except Exception as e:
            print(f"Error generating exercise candidate {candidate_id}: {e}")
            return None


# ================= Convenience Functions =================

def generate_exercise_candidates(
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {},
    user_requirement: Dict[str, Any] = {},
    num_candidates: int = 3
) -> List[ExercisePlan]:
    """
    Convenience function to generate exercise candidates.

    Args:
        user_metadata: User physiological data
        environment: Environmental context
        user_requirement: User goals
        num_candidates: Number of candidates to generate

    Returns:
        List of ExercisePlan objects
    """
    agent = ExerciseAgent()
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
            "fitness_level": "intermediate"
        },
        "environment": {
            "weather": {"condition": "clear", "temperature_c": 25},
            "time_context": {"season": "summer"}
        },
        "user_requirement": {
            "goal": "weight_loss",
            "intensity": "moderate",
            "num_candidates": 2
        }
    }

    candidates = generate_exercise_candidates(**test_input)
    print(f"Generated {len(candidates)} exercise candidates")
    for c in candidates:
        print(f"- {c.title}: {c.total_calories_burned} kcal, {c.total_duration_minutes} min")
