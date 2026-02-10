"""
Exercise Candidate Generator
Generates personalized exercise plan candidates based on user metadata and knowledge graph.
"""
import json
import os
from typing import List, Dict, Any, Optional
from agents.base import BaseAgent, DietAgentMixin, ExerciseAgentMixin
from agents.exercise.models import (
    ExerciseType, IntensityLevel, TimeOfDay, MealTiming,
    ExerciseItem, ExerciseSession, ExercisePlan,
    ExerciseCandidatesResponse, ExerciseAgentInput
)
from agents.exercise.parser import ExercisePlanParser
from core.llm import get_llm
from core.llm.utils import parse_json_response
from core.neo4j import get_kg_query
import random


# ================= Exercise Pools for Mandatory Selection =================

CARDIO_ACTIVITIES = [
    "Outdoor Running", "Treadmill Running", "Cycling (Outdoor)", "Stationary Bike",
    "Swimming (Freestyle)", "Swimming (Laps)", "Rowing Machine", "Jump Rope",
    "Hiking (Trail)", "Stair Climbing", "Elliptical Training", " Dancing (Aerobic)",
    "Boxing (Bag Work)", "Kettlebell Cardio", "Battle Ropes", "Mountain Climbers"
]

STRENGTH_MOVEMENTS = [
    "Barbell Squats", "Deadlifts", "Bench Press", "Overhead Press",
    "Pull-Ups", "Dips", "Push-Ups", "Lunges",
    "Goblet Squats", "Turkish Get-Up", "Kettlebell Swings", "Farmer's Walk",
    "Romanian Deadlifts", "Face Pulls", "Plank Variations", "Bulgarian Split Squats"
]

FLEXIBILITY_POSES = [
    "Sun Salutation Flow", "Hip Flexor Stretch", "Hamstring Stretch",
    "Cat-Cow Pose", "Child's Pose", "Pigeon Pose", "Seated Forward Fold",
    "Quad Stretch", "Chest Opener", "Thread the Needle Stretch",
    "Downward Dog", "Warrior Poses", "Balance Tree Pose", "Deep Breathing"
]

EQUIPMENT_OPTIONS = [
    "Resistance Bands", "Dumbbells", "Kettlebell", "Medicine Ball",
    "TRX Suspension", "Pull-Up Bar", "Jump Rope", "Foam Roller",
    "Yoga Mat", "Exercise Bench", "None (Bodyweight Only)"
]

OUTDOOR_ACTIVITIES = [
    "Trail Running", "Hiking", "Outdoor Cycling", "Park Workout",
    "Beach Workout", "Stair Climbing (Stadium)", "Outdoor Yoga",
    "Kayaking", "Rock Climbing (Indoor/Bouldering)"
]

WATER_ACTIVITIES = [
    "Lap Swimming", "Water Aerobics", "Treading Water", "Pool Laps"
]

HIIT_EXERCISES = [
    "Burpees", "Mountain Climbers", "Box Jumps", "High Knees",
    "Jump Squats", "Skaters", "Tuck Jumps", "Battle Ropes",
    "Sprint Intervals", "Cycle Sprints"
]

# Boring/common exercises that may be excluded for variety
COMMON_BORING_EXERCISES = [
    "Brisk Walking", "Bodyweight Squats", "Jumping Jacks", "Plank Hold",
    "Stationary Biking (Easy)", "Basic Stretching"
]


# ================= System Prompts =================

EXERCISE_GENERATION_SYSTEM_PROMPT = """You are a professional exercise prescription AI. Your task to generate personalized exercise plans based on user health data.

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
Return a valid JSON object matching the provided schema. STRICTLY follow:
- "calories_burned": TOTAL calories for this exercise (NOT per minute)
- Use lowercase for all enum values: "cardio", "strength", "low", "moderate", etc.
- "duration_minutes": Integer (not fractional)

## Example Output:
{
  "id": 1,
  "title": "Morning Cardio Plan",
  "meal_timing": "after_breakfast",
  "sessions": {
    "morning": {
      "time_of_day": "morning",
      "exercises": [
        {
          "name": "Brisk Walking",
          "exercise_type": "cardio",
          "duration_minutes": 30,
          "intensity": "low",
          "calories_burned": 135,
          "equipment": [],
          "target_muscles": ["legs", "cardio"],
          "instructions": ["Walk at comfortable pace", "Maintain good posture"],
          "reason": "Low-impact cardio suitable for beginners",
          "safety_notes": ["Stay hydrated", "Warm up first"]
        }
      ],
      "total_duration_minutes": 30,
      "total_calories_burned": 135,
      "overall_intensity": "low"
    }
  },
  "total_duration_minutes": 30,
  "total_calories_burned": 135,
  "reasoning": "This plan combines low-impact cardio with strength training",
  "safety_notes": ["Consult physician before starting", "Listen to your body"]
}

IMPORTANT:
- calories_burned should be realistic totals (e.g., 30 min walking = ~135 kcal, NOT 4-5 kcal).
- meal_timing must be one of: "before_breakfast", "after_breakfast", "before_lunch", "after_lunch", "before_dinner", "after_dinner".
- Generate only ONE session per day (single morning/afternoon/evening block).
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


# ================= Constraint Builder =================

MEAL_TIMING_OPTIONS = [
    "before_breakfast", "after_breakfast", "before_lunch", "after_lunch", "before_dinner", "after_dinner"
]

def build_exercise_constraint_prompt(
    primary_cardio: str = None,
    primary_strength: str = None,
    flexibility: str = None,
    excluded: List[str] = None,
    equipment: str = None,
    outdoor: bool = False,
    meal_timing: str = None
) -> str:
    """
    Build constraint prompt for mandatory exercise selection.

    Args:
        primary_cardio: Main cardio activity to include
        primary_strength: Main strength movement to include
        flexibility: Flexibility pose/flow to include
        excluded: List of exercises to exclude
        equipment: Required equipment to use
        outdoor: Whether to prioritize outdoor activities
        meal_timing: When to exercise relative to meals

    Returns:
        Formatted constraint string for LLM prompt
    """
    prompt_parts = []

    if meal_timing:
        timing_display = meal_timing.replace("_", " ").title()
        prompt_parts.append(f"- MEAL TIMING: {timing_display}")

    if primary_cardio:
        prompt_parts.append(f"- PRIMARY CARDIO: {primary_cardio}")

    if primary_strength:
        prompt_parts.append(f"- PRIMARY STRENGTH: {primary_strength}")

    if flexibility:
        prompt_parts.append(f"- FLEXIBILITY ELEMENT: {flexibility}")

    if equipment:
        prompt_parts.append(f"- EQUIPMENT REQUIRED: {equipment}")

    if outdoor:
        prompt_parts.append("- PRIORITIZE: Outdoor activities where possible")

    if excluded:
        prompt_parts.append(f"\n## EXCLUDED EXERCISES (DO NOT USE):")
        prompt_parts.append(f"- {', '.join(excluded)}")

    if prompt_parts:
        return "\n## EXERCISE CONSTRAINTS\n" + "\n".join(prompt_parts)

    return ""


# ================= Exercise Agent =================

class ExerciseAgent(BaseAgent, ExerciseAgentMixin):
    """Agent for generating exercise plan candidates"""

    def __init__(self):
        super().__init__()
        self.parser = ExercisePlanParser()

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
        num_variants: int = 3,
        time_of_day: str = None,
        temperature: float = 0.7,
        top_p: float = 0.92,
        top_k: int = 50
    ) -> List[ExercisePlan]:
        """
        Generate exercise plan candidates using LLM + Parser pipeline.

        Flow:
        1. Calculate target calories from user profile
        2. Query KG for exercise knowledge (conditions, restrictions)
        3. Generate ONE base exercise plan via LLM
        4. Use Parser to expand to Lite/Standard/Plus variants
        5. Build candidates

        Args:
            input_data: User metadata, environment, requirements
            num_variants: Number of portion variants (1=Lite, 2=Lite+Standard, 3=Lite+Standard+Plus)
            time_of_day: Specific time of day (morning/afternoon/evening) or None for random
            temperature: LLM temperature (0.0-1.0, default 0.7)
            top_p: LLM top_p for nucleus sampling (0.0-1.0, default 0.92)
            top_k: LLM top_k for top-k sampling (default 50)

        Returns:
            List of ExercisePlan candidates (one per variant)
        """
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

        # Define diversity pools
        available_strategies = ["balanced", "variety", "intensity_focus", "endurance", "recovery"]

        # Select strategy
        strategy = random.choice(available_strategies)

        # Determine meal timing
        if time_of_day:
            meal_timing = time_of_day
        else:
            meal_timing = random.choice(MEAL_TIMING_OPTIONS)

        # Randomly select primary exercises for mandatory injection
        primary_cardio = random.choice(CARDIO_ACTIVITIES)
        primary_strength = random.choice(STRENGTH_MOVEMENTS)
        flexibility = random.choice(FLEXIBILITY_POSES)

        # Randomly exclude boring exercises (50% chance)
        excluded = []
        if random.random() > 0.5:
            excluded = random.sample(COMMON_BORING_EXERCISES, k=random.randint(1, 2))

        # Optionally add equipment constraint (30% chance)
        equipment = None
        if random.random() > 0.7:
            equipment = random.choice(EQUIPMENT_OPTIONS)

        # Optionally prioritize outdoor (based on weather/season)
        outdoor = False
        if weather.get("condition") in ["clear", "sunny"] and random.random() > 0.5:
            outdoor = True

        # Build constraint prompt
        constraint_prompt = build_exercise_constraint_prompt(
            primary_cardio=primary_cardio,
            primary_strength=primary_strength,
            flexibility=flexibility,
            excluded=excluded,
            equipment=equipment,
            outdoor=outdoor,
            meal_timing=meal_timing
        )

        print(f"[DEBUG] Exercise: strategy={strategy}, meal_timing={meal_timing}")
        print(f"[DEBUG]   cardio={primary_cardio}, strength={primary_strength}, flexibility={flexibility}")

        # Generate ONE base plan
        base_plan = self._generate_base_plan(
            user_meta=user_meta,
            environment=env,
            requirement=requirement,
            kg_context=kg_context,
            target_calories=target_calories,
            target_duration=target_duration,
            target_frequency=target_frequency,
            fitness_level=fitness_level,
            weight=weight,
            strategy=strategy,
            meal_timing=meal_timing,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            constraint_prompt=constraint_prompt
        )

        if not base_plan:
            print("[WARN] No base plan generated")
            return []

        # Define variant names
        variant_names = ["Lite", "Standard", "Plus"][:num_variants]

        # Expand base plan to variants
        expanded_variants = self.parser.expand_plan(base_plan, variant_names)

        # Build candidates list with additional metadata
        candidates = []
        candidate_id = 1
        target_calories_pct = round((target_calories - base_plan.total_calories_burned) / target_calories * 100, 1)

        for variant_name in variant_names:
            if variant_name not in expanded_variants:
                continue

            variant_plan = expanded_variants[variant_name]

            # Build safety notes with metadata
            safety_notes = [
                f"Variant: {variant_name}",
                f"Strategy: {strategy}",
                f"Meal Timing: {meal_timing}"
            ]
            if excluded:
                safety_notes.append(f"Excluded: {', '.join(excluded)}")
            if abs(target_calories_pct) > 10:
                safety_notes.append(f"Calorie deviation: {target_calories_pct}%")

            # Add safety notes to the variant
            variant_plan.safety_notes = safety_notes

            # Set ID
            variant_plan.id = candidate_id
            candidate_id += 1

            candidates.append(variant_plan)

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
        target_frequency: int,
        meal_timing: str = None
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
**Meal Timing**: {meal_timing if meal_timing else 'any'}

## Environment Context
**Weather**: {environment.get('weather', {})}
**Season**: {environment.get('time_context', {}).get('season', 'any')}

{kg_context}

## Task
Generate a single exercise plan candidate. Return ONLY the JSON object, NO markdown code blocks, NO extra wrapper keys.
Each exercise MUST have: "name", "exercise_type", "duration_minutes", "intensity", "calories_burned".
Generate ONLY ONE session per day (single morning/afternoon/evening block).

Example format:
{{
  "id": 1,
  "title": "Morning Cardio Plan",
  "meal_timing": "after_breakfast",
  "sessions": {{
    "morning": {{
      "time_of_day": "morning",
      "exercises": [
        {{
          "name": "Brisk Walking",
          "exercise_type": "cardio",
          "duration_minutes": 30,
          "intensity": "low",
          "calories_burned": 135,
          "equipment": [],
          "target_muscles": ["legs", "cardio"],
          "instructions": ["Walk at comfortable pace", "Maintain good posture"],
          "reason": "Low-impact cardio suitable for beginners",
          "safety_notes": ["Stay hydrated", "Warm up first"]
        }}
      ],
      "total_duration_minutes": 30,
      "total_calories_burned": 135,
      "overall_intensity": "low"
    }}
  }},
  "total_duration_minutes": 30,
  "total_calories_burned": 135,
  "reasoning": "This plan combines low-impact cardio with strength training",
  "safety_notes": ["Consult physician before starting", "Listen to your body"]
}}"""

        return prompt

    def _normalize_enum_values(self, data: Dict) -> Dict:
        """Normalize enum values to lowercase (LLM may return UPPERCASE)"""
        exercise_type_map = {
            "CARDIO": "cardio", "STRENGTH": "strength", "FLEXIBILITY": "flexibility",
            "BALANCE": "balance", "HIIT": "hiit"
        }
        intensity_map = {
            "LOW": "low", "MODERATE": "moderate", "HIGH": "high", "VERY_HIGH": "very_high"
        }
        time_map = {
            "MORNING": "morning", "AFTERNOON": "afternoon", "EVENING": "evening", "ANY": "any"
        }
        meal_timing_map = {
            "BEFORE_BREAKFAST": "before_breakfast", "AFTER_BREAKFAST": "after_breakfast",
            "BEFORE_LUNCH": "before_lunch", "AFTER_LUNCH": "after_lunch",
            "BEFORE_DINNER": "before_dinner", "AFTER_DINNER": "after_dinner"
        }

        def normalize_item(exercise: Dict) -> Dict:
            if exercise.get("exercise_type") in exercise_type_map:
                exercise["exercise_type"] = exercise_type_map[exercise["exercise_type"]]
            if exercise.get("intensity") in intensity_map:
                exercise["intensity"] = intensity_map[exercise["intensity"]]
            return exercise

        def normalize_session(session: Dict) -> Dict:
            if "overall_intensity" in session:
                session["overall_intensity"] = intensity_map.get(
                    session["overall_intensity"], session["overall_intensity"]
                )
            if "exercises" in session:
                session["exercises"] = [normalize_item(ex) for ex in session["exercises"]]
            return session

        if "sessions" in data:
            for key, session in data["sessions"].items():
                data["sessions"][key] = normalize_session(session)

        # Normalize meal_timing
        if data.get("meal_timing") in meal_timing_map:
            data["meal_timing"] = meal_timing_map[data["meal_timing"]]

        return data

    def _generate_base_plan(
        self,
        user_meta: Dict[str, Any],
        environment: Dict[str, Any],
        requirement: Dict[str, Any],
        kg_context: str,
        target_calories: int,
        target_duration: int,
        target_frequency: int,
        fitness_level: str,
        weight: float,
        strategy: str = "balanced",
        meal_timing: str = None,
        temperature: float = 0.7,
        top_p: float = 0.92,
        top_k: int = 50,
        constraint_prompt: str = ""
    ) -> Optional[ExercisePlan]:
        """Generate a single base exercise plan with diversity injection"""
        strategy_guidance = {
            "balanced": "Focus on mix of cardio, strength, and flexibility.",
            "variety": "Include diverse exercises to prevent boredom and plateaus.",
            "intensity_focus": "Emphasize appropriate intensity for fitness level.",
            "endurance": "Focus on longer duration exercises for stamina building.",
            "recovery": "Emphasize low-intensity, mobility-focused exercises."
        }

        user_prompt = self._build_exercise_prompt(
            user_meta=user_meta,
            environment=environment,
            requirement=requirement,
            kg_context=kg_context,
            target_calories=target_calories,
            target_duration=target_duration,
            target_frequency=target_frequency,
            meal_timing=meal_timing
        )

        full_prompt = user_prompt + f"\n\n### Strategy: {strategy.upper()}\n{strategy_guidance.get(strategy, 'Focus on balanced training.')}"
        full_prompt += constraint_prompt

        # Call LLM
        try:
            response = self._call_llm(
                system_prompt=EXERCISE_GENERATION_SYSTEM_PROMPT,
                user_prompt=full_prompt,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k
            )

            # Handle empty response
            if not response or response == {}:
                print("[WARN] LLM returned empty response for base plan")
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

            # Normalize enum values (LLM may return UPPERCASE)
            plan_data = self._normalize_enum_values(plan_data)

            # Ensure ID is set (will be reassigned when expanding to variants)
            plan_data["id"] = 0

            # Create ExercisePlan object
            return ExercisePlan(**plan_data)

        except Exception as e:
            print(f"Error generating exercise base plan: {e}")
            return None


# ================= Convenience Functions =================

def generate_exercise_candidates(
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {},
    user_requirement: Dict[str, Any] = {},
    num_variants: int = 3,
    time_of_day: str = None,
    temperature: float = 0.7,
    top_p: float = 0.92,
    top_k: int = 50
) -> List[ExercisePlan]:
    """
    Convenience function to generate exercise candidates.

    Args:
        user_metadata: User physiological data
        environment: Environmental context
        user_requirement: User goals
        num_variants: Number of portion variants (1=Lite, 2=Lite+Standard, 3=Lite+Standard+Plus)
        time_of_day: Specific time of day (morning/afternoon/evening) or None for random
        temperature: LLM temperature (0.0-1.0, default 0.7)
        top_p: LLM top_p for nucleus sampling (0.0-1.0, default 0.92)
        top_k: LLM top_k for top-k sampling (default 50)

    Returns:
        List of ExercisePlan objects (variants of a single base plan)
    """
    agent = ExerciseAgent()
    input_data = {
        "user_metadata": user_metadata,
        "environment": environment,
        "user_requirement": user_requirement,
    }
    return agent.generate(
        input_data,
        num_variants=num_variants,
        time_of_day=time_of_day,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k
    )


def generate_exercise_variants(
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {},
    user_requirement: Dict[str, Any] = {},
    num_variants: int = 3,
    time_of_day: str = None,
    temperature: float = 0.7,
    top_p: float = 0.92,
    top_k: int = 50
) -> Dict[str, List[ExercisePlan]]:
    """
    Generate exercise plans with intensity variants (Lite/Standard/Plus).

    Args:
        user_metadata: User physiological data
        environment: Environmental context
        user_requirement: User goals
        num_variants: Number of portion variants (1=Lite, 2=Lite+Standard, 3=Lite+Standard+Plus)
        time_of_day: Specific time of day (morning/afternoon/evening) or None for random
        temperature: LLM temperature (0.0-1.0, default 0.7)
        top_p: LLM top_p for nucleus sampling (0.0-1.0, default 0.92)
        top_k: LLM top_k for top-k sampling (default 50)

    Returns:
        Dict mapping candidate_id to dict of variants:
        {
            1: {"Lite": ExercisePlan, "Standard": ExercisePlan, "Plus": ExercisePlan},
            2: {...},
            ...
        }
    """
    # Generate base plan (single plan, not multiple candidates)
    base_plan_candidates = generate_exercise_candidates(
        user_metadata, environment, user_requirement,
        num_variants=1,  # Get just one base plan
        time_of_day=time_of_day,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k
    )

    if not base_plan_candidates:
        return {}

    base_plan = base_plan_candidates[0]

    # Expand the base plan into variants
    parser = ExercisePlanParser()
    variant_names = ["Lite", "Standard", "Plus"][:num_variants]
    variants = parser.expand_plan(base_plan, variant_names)

    return {base_plan.id: variants}


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
            "intensity": "moderate"
        }
    }

    candidates = generate_exercise_candidates(
        user_metadata=test_input["user_metadata"],
        environment=test_input["environment"],
        user_requirement=test_input["user_requirement"],
        num_variants=3,
        time_of_day="after_breakfast"
    )
    print(f"Generated {len(candidates)} exercise variants")
    for c in candidates:
        print(f"- {c.title}: {c.total_calories_burned} kcal, {c.total_duration_minutes} min")
