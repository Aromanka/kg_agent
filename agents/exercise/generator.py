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
from core.llm.utils import parse_json_response
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
        "endurance": 350,
        "general_fitness": 250,
        "maintenance": 150
    }

    return goal_targets.get(goal, 200)


# ================= Exercise Agent =================

class ExerciseAgent(BaseAgent, ExerciseAgentMixin):
    """Agent for generating exercise plan candidates"""

    # ================= Target Calculation Methods =================

    def calculate_target_calories(
        self,
        weight_kg: float,
        goal: str = "maintenance"
    ) -> int:
        """
        Calculate target daily calories to burn based on goal.

        Args:
            weight_kg: User weight in kg
            goal: fitness goal (weight_loss, muscle_building, cardio_improvement, etc.)

        Returns:
            Target daily calories to burn
        """
        goal_targets = {
            "weight_loss": 400,
            "muscle_building": 200,
            "cardio_improvement": 450,
            "flexibility": 100,
            "endurance": 400,
            "general_fitness": 250,
            "maintenance": 150
        }

        # Apply condition adjustments
        conditions = []
        if hasattr(self, '_input_meta'):
            conditions = self._input_meta.get("medical_conditions", [])

        # Reduce targets for certain conditions
        reduction_factor = 1.0
        for condition in conditions:
            if condition.lower() in ["heart_disease", "obesity", "arthritis"]:
                reduction_factor = 0.75

        return int(goal_targets.get(goal, 250) * reduction_factor)

    def calculate_target_duration(
        self,
        fitness_level: str = "beginner",
        goal: str = "maintenance"
    ) -> int:
        """
        Calculate target exercise duration in minutes based on fitness level and goal.

        Args:
            fitness_level: beginner, intermediate, advanced
            goal: fitness goal

        Returns:
            Target duration in minutes per session
        """
        # Base duration by fitness level (minutes)
        base_durations = {
            "beginner": 20,
            "intermediate": 40,
            "advanced": 60
        }

        # Goal multipliers
        goal_multipliers = {
            "weight_loss": 1.0,
            "muscle_building": 0.85,
            "cardio_improvement": 1.1,
            "flexibility": 0.7,
            "endurance": 1.0,
            "general_fitness": 1.0,
            "maintenance": 0.9
        }

        base = base_durations.get(fitness_level.lower(), 30)
        multiplier = goal_multipliers.get(goal.lower(), 1.0)

        return int(base * multiplier)

    def calculate_target_weekly_frequency(
        self,
        fitness_level: str = "beginner",
        goal: str = "maintenance",
        conditions: List[str] = None
    ) -> int:
        """
        Calculate recommended weekly exercise frequency.

        Args:
            fitness_level: User fitness level
            goal: Fitness goal
            conditions: Medical conditions

        Returns:
            Sessions per week
        """
        # Base frequency by fitness level
        base_freq = {
            "beginner": 3,
            "intermediate": 4,
            "advanced": 5
        }

        # Goal adjustments
        goal_adjustments = {
            "weight_loss": 1,
            "muscle_building": 0,
            "cardio_improvement": 1,
            "flexibility": 0,
            "endurance": 1,
            "maintenance": -1
        }

        # Condition restrictions
        condition_restrictions = {
            "heart_disease": -2,
            "obesity": -1,
            "arthritis": -1,
            "back_pain": 0
        }

        freq = base_freq.get(fitness_level.lower(), 3)
        freq += goal_adjustments.get(goal.lower(), 0)

        if conditions:
            for cond in conditions:
                cond_lower = cond.lower()
                for key, adj in condition_restrictions.items():
                    if key in cond_lower or cond_lower in key:
                        freq = max(1, freq + adj)
                        break

        return max(1, min(7, freq))

    def get_strategies_for_goal(self, goal: str) -> List[str]:
        """
        Get generation strategies based on user goal.

        Args:
            goal: Fitness goal

        Returns:
            List of strategy names
        """
        strategy_map = {
            "weight_loss": ["calorie_burn", "variety", "sustainability"],
            "muscle_building": ["progressive_overload", "variety", "recovery"],
            "cardio_improvement": ["intervals", "endurance", "variety"],
            "flexibility": ["mobility", "balance", "recovery"],
            "endurance": ["progressive", "variety", "intensity"],
            "general_fitness": ["balanced", "variety", "progressive"],
            "maintenance": ["balanced", "sustainability", "variety"]
        }
        return strategy_map.get(goal.lower(), ["balanced", "variety"])

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
        self._input_meta = input_obj.user_metadata  # Store for condition access

        user_meta = input_obj.user_metadata
        env = input_obj.environment
        requirement = input_obj.user_requirement

        # Extract key parameters
        conditions = user_meta.get("medical_conditions", [])
        fitness_level = user_meta.get("fitness_level", "beginner")
        weight = user_meta.get("weight_kg", 70)
        goal = requirement.get("goal", "maintenance")
        preferred_intensity = requirement.get("intensity", "moderate")

        # Calculate target metrics using instance methods
        target_calories = self.calculate_target_calories(weight, goal)
        target_duration = self.calculate_target_duration(fitness_level, goal)
        target_frequency = self.calculate_target_weekly_frequency(fitness_level, goal, conditions)
        strategies = self.get_strategies_for_goal(goal)

        # Get knowledge graph context using mixin
        kg_context = ""
        if conditions:
            exercise_knowledge = self.query_exercise_knowledge(conditions, fitness_level)
            kg_context = self._format_kg_context(exercise_knowledge)

        # Get environment context
        weather = env.get("weather", {})
        season = env.get("time_context", {}).get("season", "any")

        # Build user prompt
        user_prompt = self._build_exercise_prompt(
            user_meta=user_meta,
            environment=env,
            requirement=requirement,
            kg_context=kg_context,
            target_calories=target_calories,
            target_duration=target_duration,
            target_frequency=target_frequency
        )

        # Generate candidates using LLM
        candidates = []
        strategies = strategies[:num_candidates] if num_candidates > 1 else [strategies[0]] if strategies else ["balanced"]

        for i in range(num_candidates):
            strategy = strategies[i % len(strategies)] if strategies else "balanced"

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

    def _format_kg_context(self, knowledge: Dict) -> str:
        """Format KG knowledge for prompt inclusion"""
        context = "\n## Knowledge Graph Context\n"

        if knowledge.get("recommended_exercises"):
            exercises = [e.get("exercise", "") for e in knowledge["recommended_exercises"]]
            context += f"- Recommended exercises: {', '.join(set(exercises))}\n"

        if knowledge.get("avoid_exercises"):
            avoids = [a.get("exercise", "") for a in knowledge["avoid_exercises"]]
            context += f"- Avoid: {', '.join(set(avoids))}\n"

        if knowledge.get("intensity_recommendations"):
            for rec in knowledge["intensity_recommendations"][:3]:
                context += f"- Intensity for {rec.get('condition', 'general')}: {rec.get('recommended_intensity')}\n"

        if knowledge.get("condition_specific_notes"):
            for note in knowledge["condition_specific_notes"][:2]:
                context += f"- Note: {note.get('note', '')}\n"

        return context

    def _build_exercise_prompt(
        self,
        user_meta: Dict[str, Any],
        environment: Dict[str, Any],
        requirement: Dict[str, Any],
        kg_context: str,
        target_calories: int,
        target_duration: int,
        target_frequency: int
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
**Target Duration**: {target_duration} minutes per session
**Weekly Frequency**: {target_frequency} sessions per week

## Environment Context
**Weather**: {environment.get('weather', {})}
**Season**: {environment.get('time_context', {}).get('season', 'any')}

{kg_context}

## Task
Generate a single exercise plan candidate. Return ONLY the JSON object, NO markdown code blocks, NO extra wrapper keys.
Each exercise MUST have: "name", "exercise_type", "duration_minutes", "intensity", "calories_burned".

Example format:
{{
  "id": 1,
  "title": "Morning Cardio Plan",
  "sessions": {{
    "morning": {{
      "time_of_day": "morning",
      "exercises": [
        {{
          "name": "Brisk Walking",
          "exercise_type": "cardio",
          "duration_minutes": 30,
          "intensity": "low",
          "calories_burned": 150,
          "equipment": [],
          "target_muscles": ["legs", "cardio"],
          "instructions": ["Walk at comfortable pace", "Maintain good posture"],
          "reason": "Low-impact cardio suitable for beginners",
          "safety_notes": ["Stay hydrated", "Warm up first"]
        }}
      ],
      "total_duration_minutes": 30,
      "total_calories_burned": 150,
      "overall_intensity": "low"
    }},
    "afternoon": {{
      "time_of_day": "afternoon",
      "exercises": [
        {{
          "name": "Bodyweight Squats",
          "exercise_type": "strength",
          "duration_minutes": 15,
          "intensity": "moderate",
          "calories_burned": 80,
          "equipment": [],
          "target_muscles": ["legs", "core"],
          "instructions": ["Keep back straight", "Lower until thighs parallel"],
          "safety_notes": ["Avoid deep knee bend if knee issues"]
        }}
      ],
      "total_duration_minutes": 15,
      "total_calories_burned": 80,
      "overall_intensity": "moderate"
    }}
  }},
  "total_duration_minutes": 45,
  "total_calories_burned": 230,
  "weekly_frequency": 5,
  "progression": "Week 1-2: Establish baseline. Week 3-4: Increase duration by 5min/session",
  "reasoning": "This plan combines low-impact cardio with strength training",
  "safety_notes": ["Consult physician before starting", "Listen to your body"]
}}"""

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
            "variety": "Include diverse exercises to prevent boredom and plateaus.",
            "intensity_focus": "Emphasize appropriate intensity for fitness level."
        }

        full_prompt = user_prompt + f"\n\n### Strategy: {strategy.upper()}\n{strategy_guidance.get(strategy, 'Focus on balanced training.')}"

        # Call LLM
        try:
            response = self._call_llm(
                system_prompt=EXERCISE_GENERATION_SYSTEM_PROMPT,
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
