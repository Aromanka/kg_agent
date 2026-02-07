"""
Diet Pipeline
Generates lunch options with safety assessment and selection.

Flow:
1. Generate multiple lunch base plans via LLM
2. Expand each base plan to Lite/Standard/Plus variants
3. Assess each variant through safeguard
4. Select top_k (default 3) by safety score
5. Output all expanded plans to plan.json
6. Output chosen plans to terminal
"""
import json
import os
from typing import List, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from agents.diet import generate_diet_candidates
from agents.diet.models import DietRecommendation
from agents.safeguard.assessor import SafeguardAgent
from agents.safeguard.models import SafetyAssessment


# ================= Pipeline Output =================

@dataclass
class DietPipelineOutput:
    """Output from the diet pipeline"""
    all_plans: List[Dict[str, Any]]      # All expanded plans (for plan.json)
    top_plans: List[Dict[str, Any]]       # Top K selected plans
    assessments: Dict[int, Dict[str, Any]]  # Safety assessments by plan ID
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling datetime serialization"""
        def convert_datetime(obj):
            """Recursively convert datetime to ISO string"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetime(item) for item in obj]
            return obj

        return {
            "all_plans": convert_datetime(self.all_plans),
            "top_plans": convert_datetime(self.top_plans),
            "assessments": convert_datetime(self.assessments),
            "generated_at": self.generated_at
        }


# ================= Diet Pipeline =================

class DietPipeline:
    """
    Pipeline for generating and evaluating lunch options.

    Generates multiple lunch candidates via LLM, expands them to
    portion variants, assesses safety, and selects the best ones.
    """

    def __init__(self):
        self.safeguard = SafeguardAgent()

    def generate(
        self,
        user_metadata: Dict[str, Any],
        environment: Dict[str, Any] = None,
        user_requirement: Dict[str, Any] = None,
        num_base_plans: int = 3,
        num_variants: int = 3,
        top_k: int = 3,
        output_path: str = "plan.json"
    ) -> DietPipelineOutput:
        """
        Generate lunch options with safety assessment.

        Args:
            user_metadata: User physiological data
            environment: Environmental context
            user_requirement: User goals
            num_base_plans: Number of LLM-generated base plans
            num_variants: Number of portion variants per base (Lite/Standard/Plus)
            top_k: Number of top plans to select
            output_path: Path to save all plans JSON

        Returns:
            DietPipelineOutput with all plans, top plans, and assessments
        """
        env = environment or {}
        req = user_requirement or {}

        print("=" * 60)
        print("DIET PIPELINE")
        print("=" * 60)

        # Step 1: Generate lunch candidates with variants
        print(f"\n[1/4] Generating {num_base_plans} lunch base plans...")
        all_candidates = generate_diet_candidates(
            user_metadata=user_metadata,
            environment=env,
            user_requirement=req,
            num_variants=num_variants  # Lite/Standard/Plus per base plan
        )

        # Filter only lunch candidates
        lunch_candidates = [c for c in all_candidates if c.meal_type == "lunch"]
        print(f"      Found {len(lunch_candidates)} lunch candidates")

        if not lunch_candidates:
            print("[WARN] No lunch candidates generated!")
            return DietPipelineOutput(
                all_plans=[],
                top_plans=[],
                assessments={},
                generated_at=datetime.now().isoformat()
            )

        # Convert to dicts for assessment
        all_plans_dict = [c.model_dump() for c in lunch_candidates]

        # Step 2: Assess each plan through safeguard
        print(f"\n[2/4] Assessing {len(all_plans_dict)} plans through safeguard...")
        assessments: Dict[int, Dict[str, Any]] = {}
        for plan in all_plans_dict:
            plan_id = plan.get("id", 0)
            assessment = self.safeguard.assess(
                plan=plan,
                plan_type="diet",
                user_metadata=user_metadata,
                environment=env
            )
            assessments[plan_id] = assessment.model_dump()
            score = assessment.score
            is_safe = assessment.is_safe
            risk = assessment.risk_level.value
            print(f"      ID:{plan_id} {plan.get('variant', 'N/A')} | "
                  f"Score:{score} | Risk:{risk} | Safe:{is_safe}")

        # Add assessment info to plans
        for plan in all_plans_dict:
            plan_id = plan.get("id", 0)
            if plan_id in assessments:
                plan["_assessment"] = assessments[plan_id]

        # Step 3: Select top_k by safety score
        print(f"\n[3/4] Selecting top {top_k} plans by safety score...")

        # Sort by score (higher first)
        sorted_plans = sorted(
            all_plans_dict,
            key=lambda p: p.get("_assessment", {}).get("score", 0),
            reverse=True
        )
        top_plans = sorted_plans[:top_k]

        for i, plan in enumerate(top_plans, 1):
            score = plan.get("_assessment", {}).get("score", 0)
            variant = plan.get("variant", "N/A")
            print(f"      #{i} ID:{plan.get('id')} {variant} | Score:{score}")

        # Step 4: Save all plans to JSON
        print(f"\n[4/4] Saving all {len(all_plans_dict)} plans to {output_path}...")
        output = DietPipelineOutput(
            all_plans=all_plans_dict,
            top_plans=top_plans,
            assessments=assessments,
            generated_at=datetime.now().isoformat()
        )

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"      Saved to {output_path}")

        return output

    def print_top_plans(self, output: DietPipelineOutput):
        """Print the top selected plans to terminal"""
        print("\n" + "=" * 60)
        print("TOP SELECTED LUNCH PLANS")
        print("=" * 60)

        for i, plan in enumerate(output.top_plans, 1):
            assessment = plan.get("_assessment", {})
            print(f"\n#{i} Plan ID:{plan.get('id')} | {plan.get('variant', 'N/A')}")
            print(f"   Safety Score: {assessment.get('score', 'N/A')}/100")
            print(f"   Risk Level: {assessment.get('risk_level', 'N/A')}")
            print(f"   Safe: {'Yes' if assessment.get('is_safe') else 'No'}")
            print(f"   Calories: {plan.get('total_calories', 'N/A')} "
                  f"(Target: {plan.get('target_calories', 'N/A')}) "
                  f"Deviation: {plan.get('calories_deviation', 0)}%")

            print("   Food Items:")
            for item in plan.get("items", []):
                print(f"     - {item.get('food', 'N/A')}: "
                      f"{item.get('portion', 'N/A')} ({item.get('calories', 0)} kcal)")

            if assessment.get("risk_factors"):
                print(f"   Risk Factors:")
                for rf in assessment.get("risk_factors", [])[:3]:
                    print(f"     - {rf}")

            if assessment.get("recommendations"):
                print(f"   Recommendations:")
                for rec in assessment.get("recommendations", [])[:2]:
                    print(f"     - {rec}")


# ================= Convenience Function =================

def run_diet_pipeline(
    user_metadata: Dict[str, Any],
    environment: Dict[str, Any] = None,
    user_requirement: Dict[str, Any] = None,
    num_base_plans: int = 3,
    num_variants: int = 3,
    top_k: int = 3,
    output_path: str = "plan.json",
    print_results: bool = True
) -> DietPipelineOutput:
    """
    Run the diet pipeline and optionally print results.

    Args:
        user_metadata: User physiological data
        environment: Environmental context
        user_requirement: User goals
ans: Number of LLM-generated base        num_base_pl plans
        num_variants: Number of portion variants per base
        top_k: Number of top plans to select
        output_path: Path to save all plans JSON
        print_results: Whether to print top plans to terminal

    Returns:
        DietPipelineOutput object
    """
    pipeline = DietPipeline()
    output = pipeline.generate(
        user_metadata=user_metadata,
        environment=environment,
        user_requirement=user_requirement,
        num_base_plans=num_base_plans,
        num_variants=num_variants,
        top_k=top_k,
        output_path=output_path
    )

    if print_results:
        pipeline.print_top_plans(output)

    return output


# ================= CLI =================

if __name__ == "__main__":
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
        "num_base_plans": 3,
        "num_variants": 3,
        "top_k": 3,
        "output_path": "plan.json"
    }

    result = run_diet_pipeline(**test_input)
    print(f"\nTotal plans generated: {len(result.all_plans)}")
    print(f"Top plans selected: {len(result.top_plans)}")
