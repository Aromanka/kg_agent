"""
Safeguard Agent - Safety Assessment Module
Evaluates plan safety based on user metadata, environment, and plan content.
Provides 0-100 safety score and True/False safety judgment.
"""
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from agents.base import BaseAgent
from agents.safeguard.models import (
    RiskLevel, AssessmentStatus,
    RiskFactor, SafetyCheck, SafetyAssessment,
    SafeguardInput, SafeguardResponse
)
from core.llm import get_llm
from core.neo4j import get_kg_query


# ================= Safety Rules =================

# Rule-based safety thresholds
DIET_SAFETY_RULES = {
    "min_calories": {
        "value": 1200,
        "message": "Daily calories too low",
        "severity": RiskLevel.HIGH
    },
    "max_calories": {
        "value": 4000,
        "message": "Daily calories too high",
        "severity": RiskLevel.MODERATE
    },
    "min_protein_ratio": {
        "value": 0.10,
        "message": "Protein ratio too low (need adequate protein)",
        "severity": RiskLevel.MODERATE
    },
    "max_fat_ratio": {
        "value": 0.40,
        "message": "Fat ratio too high",
        "severity": RiskLevel.MODERATE
    },
    "single_meal_calories": {
        "value": 1500,
        "message": "Single meal calorie too high",
        "severity": RiskLevel.LOW
    }
}

EXERCISE_SAFETY_RULES = {
    "max_daily_duration_beginner": {
        "value": 30,
        "message": "Exercise duration too long for beginner",
        "severity": RiskLevel.HIGH
    },
    "max_daily_duration_intermediate": {
        "value": 60,
        "message": "Exercise duration too long",
        "severity": RiskLevel.MODERATE
    },
    "max_daily_duration_advanced": {
        "value": 120,
        "message": "Exercise duration excessive",
        "severity": RiskLevel.LOW
    },
    "min_rest_between_hiit": {
        "value": 48,
        "message": "HIIT sessions too frequent (need rest days)",
        "severity": RiskLevel.HIGH
    },
    "max_weekly_sessions": {
        "value": 7,
        "message": "Daily exercise without rest (need rest days)",
        "severity": RiskLevel.MODERATE
    }
}

# Condition-specific restrictions
CONDITION_RESTRICTIONS = {
    "diabetes": {
        "diet": {
            "avoid_high_sugar": "High sugar foods",
            "avoid_irregular_meals": "Irregular meal timing"
        },
        "exercise": {
            "avoid_vigorous_if_below_100": "Vigorous exercise with blood sugar < 100mg/dL",
            "avoid_late_exercise": "Late night exercise (hypoglycemia risk)"
        }
    },
    "hypertension": {
        "diet": {
            "max_sodium": 2300,
            "avoid_high_sodium": "High sodium foods"
        },
        "exercise": {
            "avoid_isometric": "Isometric exercises (heavy static holds)",
            "avoid_valsalva": "Breath holding during exercise"
        }
    },
    "heart_disease": {
        "exercise": {
            "max_heart_rate": "220 - age * 0.7",
            "avoid_high_intensity": "High intensity exercise",
            "require_clearance": "Medical clearance required"
        }
    },
    "obesity": {
        "exercise": {
            "avoid_high_impact": "High impact exercises",
            "start_low": "Low impact, gradual progression"
        }
    },
    "arthritis": {
        "exercise": {
            "avoid_high_impact": "Running, jumping",
            "prefer_low_impact": "Swimming, cycling"
        }
    }
}


# ================= Safeguard Agent =================

class SafeguardAgent(BaseAgent):
    """Agent for safety assessment of diet and exercise plans"""

    def get_agent_name(self) -> str:
        return "safeguard"

    def get_input_type(self):
        return SafeguardInput

    def get_output_type(self):
        return SafetyAssessment

    def assess(
        self,
        plan: Dict[str, Any],
        plan_type: str,
        user_metadata: Dict[str, Any],
        environment: Dict[str, Any] = {}
    ) -> SafetyAssessment:
        """
        Assess safety of a plan.

        Args:
            plan: The plan to assess (dict)
            plan_type: 'diet' or 'exercise'
            user_metadata: User physiological data
            environment: Environmental context

        Returns:
            SafetyAssessment object with score and risk factors
        """
        # Initialize checks and risk factors
        checks = []
        risk_factors = []

        # Run rule-based checks
        if plan_type == "diet":
            rule_checks, rule_risks = self._check_diet_safety(
                plan, user_metadata
            )
        elif plan_type == "exercise":
            rule_checks, rule_risks = self._check_exercise_safety(
                plan, user_metadata
            )
        else:
            rule_checks, rule_risks = [], []

        checks.extend(rule_checks)
        risk_factors.extend(rule_risks)

        # Run condition-specific checks
        condition_checks, condition_risks = self._check_condition_restrictions(
            plan, plan_type, user_metadata
        )
        checks.extend(condition_checks)
        risk_factors.extend(condition_risks)

        # Run environment checks
        env_checks, env_risks = self._check_environment_safety(
            plan, plan_type, environment
        )
        checks.extend(env_checks)
        risk_factors.extend(env_risks)

        # Calculate score
        passed_checks = sum(1 for c in checks if c.passed)
        total_checks = len(checks) if checks else 1

        # Base score from rule checks
        base_score = (passed_checks / total_checks) * 100 if total_checks > 0 else 100

        # Apply severity penalties
        severity_penalty = 0
        for rf in risk_factors:
            penalty = {"low": 5, "moderate": 15, "high": 30, "very_high": 50}
            severity_penalty += penalty.get(rf.severity.value, 0)

        # LLM semantic assessment for additional insights
        llm_assessment = self._llm_semantic_assessment(
            plan, plan_type, user_metadata, environment
        )

        # Merge LLM findings
        if llm_assessment:
            risk_factors.extend(llm_assessment.get("risk_factors", []))
            checks.extend(llm_assessment.get("checks", []))

        # Final score calculation
        final_score = max(0, min(100, base_score - severity_penalty))

        # Determine if safe
        is_safe = final_score >= 60 and not any(
            rf.severity in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]
            for rf in risk_factors
        )

        # Determine status
        if final_score >= 80:
            status = AssessmentStatus.PASSED
        elif final_score >= 60:
            status = AssessmentStatus.WARNING
        elif final_score >= 40:
            status = AssessmentStatus.REVIEW
        else:
            status = AssessmentStatus.FAILED

        # Determine risk level
        if final_score >= 80:
            risk_level = RiskLevel.LOW
        elif final_score >= 60:
            risk_level = RiskLevel.MODERATE
        elif final_score >= 40:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.VERY_HIGH

        # Generate recommendations
        recommendations = self._generate_recommendations(
            risk_factors, plan_type, user_metadata
        )

        return SafetyAssessment(
            score=final_score,
            is_safe=is_safe,
            status=status,
            risk_level=risk_level,
            risk_factors=risk_factors,
            safety_checks=checks,
            recommendations=recommendations,
            warnings=[rf.description for rf in risk_factors if rf.severity in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]]
        )

    def _check_diet_safety(
        self,
        plan: Dict[str, Any],
        user_metadata: Dict[str, Any]
    ) -> tuple:
        """Run diet-specific safety checks"""
        checks = []
        risk_factors = []

        total_calories = plan.get("total_calories", 0)

        # Calorie range check
        if total_calories < DIET_SAFETY_RULES["min_calories"]["value"]:
            checks.append(SafetyCheck(
                check_name="min_calories",
                passed=False,
                message=DIET_SAFETY_RULES["min_calories"]["message"],
                severity=RiskLevel.HIGH
            ))
            risk_factors.append(RiskFactor(
                factor="extremely_low_calories",
                category="nutritional",
                severity=RiskLevel.HIGH,
                description=f"Total calories {total_calories} is dangerously low",
                recommendation="Consult a dietitian for safe calorie targets"
            ))
        elif total_calories > DIET_SAFETY_RULES["max_calories"]["value"]:
            checks.append(SafetyCheck(
                check_name="max_calories",
                passed=False,
                message=DIET_SAFETY_RULES["max_calories"]["message"],
                severity=RiskLevel.MODERATE
            ))
        else:
            checks.append(SafetyCheck(
                check_name="calories_range",
                passed=True,
                message="Calorie intake within acceptable range"
            ))

        # Macro ratio checks
        macros = plan.get("macro_nutrients", {})
        if macros:
            protein_ratio = macros.get("protein_ratio", 0)
            fat_ratio = macros.get("fat_ratio", 0)

            if protein_ratio < DIET_SAFETY_RULES["min_protein_ratio"]["value"]:
                risk_factors.append(RiskFactor(
                    factor="low_protein",
                    category="nutritional",
                    severity=RiskLevel.MODERATE,
                    description=f"Protein ratio {protein_ratio*100:.1f}% is below recommended minimum",
                    recommendation="Include more protein-rich foods"
                ))

            if fat_ratio > DIET_SAFETY_RULES["max_fat_ratio"]["value"]:
                risk_factors.append(RiskFactor(
                    factor="high_fat",
                    category="nutritional",
                    severity=RiskLevel.MODERATE,
                    description=f"Fat ratio {fat_ratio*100:.1f}% exceeds recommended maximum",
                    recommendation="Reduce high-fat foods"
                ))

        return checks, risk_factors

    def _check_exercise_safety(
        self,
        plan: Dict[str, Any],
        user_metadata: Dict[str, Any]
    ) -> tuple:
        """Run exercise-specific safety checks"""
        checks = []
        risk_factors = []

        fitness_level = user_metadata.get("fitness_level", "beginner")
        total_duration = plan.get("total_duration_minutes", 0)
        sessions = plan.get("sessions", {})
        weekly_freq = plan.get("weekly_frequency", 3)

        # Duration limits based on fitness level
        max_duration_map = {
            "beginner": EXERCISE_SAFETY_RULES["max_daily_duration_beginner"]["value"],
            "intermediate": EXERCISE_SAFETY_RULES["max_daily_duration_intermediate"]["value"],
            "advanced": EXERCISE_SAFETY_RULES["max_daily_duration_advanced"]["value"]
        }
        max_duration = max_duration_map.get(fitness_level, 60)

        if total_duration > max_duration:
            severity = RiskLevel.MODERATE if fitness_level == "advanced" else RiskLevel.HIGH
            checks.append(SafetyCheck(
                check_name="daily_duration",
                passed=False,
                message=f"Duration {total_duration}min exceeds {fitness_level} limit ({max_duration}min)",
                severity=severity
            ))
            risk_factors.append(RiskFactor(
                factor="excessive_duration",
                category="exercise",
                severity=severity,
                description=f"Total exercise time {total_duration}min is excessive for {fitness_level}",
                recommendation=f"Reduce daily duration to {max_duration}min or less"
            ))
        else:
            checks.append(SafetyCheck(
                check_name="daily_duration",
                passed=True,
                message=f"Duration {total_duration}min is appropriate"
            ))

        # Rest day check
        if weekly_freq > EXERCISE_SAFETY_RULES["max_weekly_sessions"]["value"]:
            checks.append(SafetyCheck(
                check_name="rest_days",
                passed=False,
                message="Exercise every day without rest",
                severity=RiskLevel.MODERATE
            ))
            risk_factors.append(RiskFactor(
                factor="no_rest_days",
                category="exercise",
                severity=RiskLevel.MODERATE,
                description="No rest days scheduled in weekly plan",
                recommendation="Include at least 1-2 rest days per week"
            ))

        # HIIT frequency check
        has_hiit = any(
            ex.get("exercise_type") == "hiit"
            for session in sessions.values()
            for ex in session.get("exercises", [])
        )
        if has_hiit and weekly_freq > 3:
            risk_factors.append(RiskFactor(
                factor="hiit_frequency",
                category="exercise",
                severity=RiskLevel.HIGH,
                description="HIIT sessions too frequent without adequate recovery",
                recommendation="Limit HIIT to 2-3 times per week with 48h rest"
            ))

        return checks, risk_factors

    def _check_condition_restrictions(
        self,
        plan: Dict[str, Any],
        plan_type: str,
        user_metadata: Dict[str, Any]
    ) -> tuple:
        """Check plan against condition-specific restrictions"""
        checks = []
        risk_factors = []

        conditions = user_metadata.get("medical_conditions", [])

        for condition in conditions:
            condition = condition.lower()
            if condition in CONDITION_RESTRICTIONS:
                restrictions = CONDITION_RESTRICTIONS[condition]

                # Check diet restrictions
                if plan_type == "diet" and "diet" in restrictions:
                    diet_rules = restrictions["diet"]
                    plan_str = str(plan).lower()

                    for rule_key, rule_desc in diet_rules.items():
                        if rule_key in ["avoid_high_sugar", "avoid_high_sodium"]:
                            if rule_key.replace("avoid_", "") in plan_str:
                                risk_factors.append(RiskFactor(
                                    factor=f"{condition}_{rule_key}",
                                    category="medical",
                                    severity=RiskLevel.HIGH,
                                    description=f"Plan contains {rule_desc} for {condition}",
                                    recommendation=f"Remove {rule_desc} for {condition} management"
                                ))

                # Check exercise restrictions
                if plan_type == "exercise" and "exercise" in restrictions:
                    ex_rules = restrictions["exercise"]
                    plan_str = str(plan).lower()

                    for rule_key, rule_desc in ex_rules.items():
                        if "avoid" in rule_key or "max" in rule_key:
                            risk_factors.append(RiskFactor(
                                factor=f"{condition}_{rule_key}",
                                category="medical",
                                severity=RiskLevel.HIGH,
                                description=f"Exercise may violate {condition} restriction: {rule_desc}",
                                recommendation=f"Modify plan to comply with {rule_desc}"
                            ))

        return checks, risk_factors

    def _check_environment_safety(
        self,
        plan: Dict[str, Any],
        plan_type: str,
        environment: Dict[str, Any]
    ) -> tuple:
        """Check plan against environmental factors"""
        checks = []
        risk_factors = []

        weather = environment.get("weather", {})
        condition = weather.get("condition", "clear")
        temperature = weather.get("temperature_c", 20)

        # Temperature-based checks for outdoor exercise
        if plan_type == "exercise":
            if temperature > 35:
                risk_factors.append(RiskFactor(
                    factor="high_temperature_exercise",
                    category="environmental",
                    severity=RiskLevel.HIGH,
                    description=f"High temperature ({temperature}°C) increases heat stress risk",
                    recommendation="Exercise indoors or in early morning/late evening"
                ))
            elif temperature < 5:
                risk_factors.append(RiskFactor(
                    factor="cold_temperature_exercise",
                    category="environmental",
                    severity=RiskLevel.MODERATE,
                    description=f"Cold temperature ({temperature}°C) increases cardiovascular strain",
                    recommendation="Warm up thoroughly, dress in layers"
                ))

            if condition == "rainy" or condition == "icy":
                risk_factors.append(RiskFactor(
                    factor="inclement_weather",
                    category="environmental",
                    severity=RiskLevel.MODERATE,
                    description=f"{condition} weather increases slip/fall risk",
                    recommendation="Move exercise indoors or choose safe surfaces"
                ))

        # Diet considerations for environment
        if plan_type == "diet":
            if temperature > 30:
                # Suggest lighter meals
                checks.append(SafetyCheck(
                    check_name="hot_weather_hydration",
                    passed=True,
                    message="Consider increased fluid intake for hot weather"
                ))

        return checks, risk_factors

    def _llm_semantic_assessment(
        self,
        plan: Dict[str, Any],
        plan_type: str,
        user_metadata: Dict[str, Any],
        environment: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Use LLM for semantic safety assessment"""
        try:
            prompt = f"""Analyze the following {plan_type} plan for safety issues.

## User Profile
- Age: {user_metadata.get('age', 'unknown')}
- Conditions: {', '.join(user_metadata.get('medical_conditions', ['none']))}
- Fitness Level: {user_metadata.get('fitness_level', 'unknown')}

## Environment
{environment}

## Plan
{json.dumps(plan, ensure_ascii=False, indent=2)}

## Task
Identify any safety concerns that rule-based checks might miss:
1. Hidden contraindications
2. Unrealistic progression
3. Nutrient deficiencies
4. Overtraining signs
5. Environmental mismatches

Return JSON with:
- "risk_factors": array of {{factor, description, severity}}
- "checks": array of {{check_name, passed, message}}"""

            response = self._call_llm(
                system_prompt="You are a safety assessment expert. Return only valid JSON.",
                user_prompt=prompt,
                temperature=0.3
            )

            if isinstance(response, str):
                return json.loads(response)
            return response

        except Exception as e:
            print(f"LLM assessment failed: {e}")
            return None

    def _generate_recommendations(
        self,
        risk_factors: List[RiskFactor],
        plan_type: str,
        user_metadata: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        for rf in risk_factors:
            recommendations.append(rf.recommendation)

        # Add general recommendations
        if user_metadata.get("medical_conditions"):
            recommendations.append(
                f"Consult healthcare provider before starting due to: {', '.join(user_metadata['medical_conditions'])}"
            )

        if plan_type == "exercise":
            recommendations.extend([
                "Start gradually and listen to your body",
                "Stay hydrated before, during, and after exercise",
                "Stop immediately if you experience pain or discomfort"
            ])

        return list(set(recommendations))  # Remove duplicates


# ================= Convenience Functions =================

def assess_plan_safety(
    plan: Dict[str, Any],
    plan_type: str,
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {}
) -> SafetyAssessment:
    """
    Convenience function to assess plan safety.

    Args:
        plan: The plan to assess
        plan_type: 'diet' or 'exercise'
        user_metadata: User physiological data
        environment: Environmental context

    Returns:
        SafetyAssessment object
    """
    agent = SafeguardAgent()
    return agent.assess(plan, plan_type, user_metadata, environment)


def combined_assessment(
    diet_plan: Optional[Dict[str, Any]],
    exercise_plan: Optional[Dict[str, Any]],
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = {}
) -> Dict[str, Any]:
    """
    Assess both diet and exercise plans together.
    Returns combined safety evaluation.
    """
    agent = SafeguardAgent()

    diet_assessment = None
    exercise_assessment = None

    if diet_plan:
        diet_assessment = agent.assess(diet_plan, "diet", user_metadata, environment)

    if exercise_plan:
        exercise_assessment = agent.assess(exercise_plan, "exercise", user_metadata, environment)

    # Calculate combined score
    assessments = [a for a in [diet_assessment, exercise_assessment] if a]
    if assessments:
        overall_score = sum(a.score for a in assessments) // len(assessments)
        is_safe = all(a.is_safe for a in assessments)
    else:
        overall_score = 100
        is_safe = True

    return {
        "diet_assessment": diet_assessment,
        "exercise_assessment": exercise_assessment,
        "overall_score": overall_score,
        "is_safe": is_safe
    }


if __name__ == "__main__":
    # Test the safeguard agent
    diet_plan = {
        "id": 1,
        "total_calories": 1500,
        "macro_nutrients": {
            "protein_ratio": 0.15,
            "carbs_ratio": 0.55,
            "fat_ratio": 0.30
        },
        "meal_plan": {}
    }

    user_metadata = {
        "age": 35,
        "medical_conditions": ["diabetes"],
        "fitness_level": "intermediate"
    }

    assessment = assess_plan_safety(
        plan=diet_plan,
        plan_type="diet",
        user_metadata=user_metadata
    )

    print(f"Score: {assessment.score}/100")
    print(f"Is Safe: {assessment.is_safe}")
    print(f"Risk Level: {assessment.risk_level.value}")
    print(f"Risk Factors: {len(assessment.risk_factors)}")
