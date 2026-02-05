#!/usr/bin/env python3
"""
CLI Entry Point for kg_agents

Usage:
    python run.py diet --help
    python run.py exercise --help
    python run.py safeguard --help
    python run.py pipeline --help
    python run.py all
"""
import argparse
import sys
from pathlib import Path
import os
from config_loader import get_config


def check_config():
    """Check if config.json exists and is valid"""
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"[ERROR] config.json not found at {config_path}")
        print("Please copy config.example.json to config.json and fill in your API keys.")
        sys.exit(1)

    try:
        config = get_config(config_path)
        print(f"[OK] Config loaded successfully")
        return config
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        sys.exit(1)


def cmd_diet(args):
    """Generate diet candidates"""
    check_config()

    from agents.diet.generator import generate_diet_candidates

    test_input = {
        "user_metadata": {
            "age": 35,
            "gender": "male",
            "height_cm": 175,
            "weight_kg": 70,
            "medical_conditions": args.conditions.split(",") if args.conditions else ["diabetes"],
            "dietary_restrictions": args.restrictions.split(",") if args.restrictions else [],
            "fitness_level": "intermediate"
        },
        "environment": {
            "weather": {"condition": "clear", "temperature_c": 25},
            "time_context": {"season": "summer"}
        },
        "user_requirement": {"goal": args.goal or "weight_loss"},
        "num_candidates": args.num or 2
    }

    print("\n=== Generating Diet Candidates ===")
    candidates = generate_diet_candidates(**test_input)

    print(f"\nGenerated {len(candidates)} candidates:")
    for c in candidates:
        print(f"  - ID: {c.id}, Calories: {c.total_calories}, Deviation: {c.calories_deviation}%")
        print(c)

    return candidates


def cmd_exercise(args):
    """Generate exercise candidates"""
    check_config()

    from agents.exercise.generator import generate_exercise_candidates

    test_input = {
        "user_metadata": {
            "age": 35,
            "gender": "male",
            "height_cm": 175,
            "weight_kg": 70,
            "medical_conditions": args.conditions.split(",") if args.conditions else [],
            "fitness_level": "intermediate"
        },
        "environment": {
            "weather": {"condition": "clear", "temperature_c": 25},
            "time_context": {"season": "summer"}
        },
        "user_requirement": {
            "goal": args.goal or "weight_loss",
            "intensity": "moderate"
        },
        "num_candidates": args.num or 2
    }

    print("\n=== Generating Exercise Candidates ===")
    candidates = generate_exercise_candidates(**test_input)

    print(f"\nGenerated {len(candidates)} candidates:")
    for c in candidates:
        print(f"  - ID: {c.id}, Calories: {c.total_calories_burned}, Duration: {c.total_duration_minutes}min")

    return candidates


def cmd_safeguard(args):
    """Run safety assessment"""
    check_config()

    from agents.safeguard.assessor import assess_plan_safety

    # Sample diet plan for testing
    test_plan = {
        "id": 1,
        "total_calories": 1800,
        "macro_nutrients": {
            "protein_ratio": 0.20,
            "carbs_ratio": 0.50,
            "fat_ratio": 0.30
        },
        "meal_plan": {}
    }

    user_metadata = {
        "age": 35,
        "medical_conditions": args.conditions.split(",") if args.conditions else ["diabetes"],
        "fitness_level": "intermediate"
    }

    environment = {
        "weather": {"temperature_c": 25}
    }

    print("\n=== Safety Assessment ===")
    assessment = assess_plan_safety(
        plan=test_plan,
        plan_type="diet",
        user_metadata=user_metadata,
        environment=environment
    )

    print(f"\nScore: {assessment.score}/100")
    print(f"Is Safe: {assessment.is_safe}")
    print(f"Risk Level: {assessment.risk_level.value}")

    if assessment.risk_factors:
        print("\nRisk Factors:")
        for rf in assessment.risk_factors:
            print(f"  - {rf.factor}: {rf.description}")

    return assessment


def cmd_pipeline(args):
    """Run full pipeline"""
    check_config()

    from pipeline.health_pipeline import generate_health_plans

    test_input = {
        "user_metadata": {
            "age": 35,
            "gender": "male",
            "height_cm": 175,
            "weight_kg": 70,
            "medical_conditions": args.conditions.split(",") if args.conditions else ["diabetes"],
            "dietary_restrictions": args.restrictions.split(",") if args.restrictions else ["low_sodium"],
            "fitness_level": "intermediate"
        },
        "environment": {
            "weather": {"condition": "clear", "temperature_c": 25},
            "time_context": {"season": "summer"}
        },
        "user_requirement": {
            "goal": args.goal or "weight_loss",
            "intensity": "moderate"
        },
        "num_candidates": args.num or 2,
        "filter_safe": not args.no_filter,
        "min_score": args.min_score or 60
    }

    print("\n=== Health Pipeline ===")
    result = generate_health_plans(**test_input)

    print(f"\nDiet candidates: {len(result['diet_candidates'])}")
    print(f"Exercise candidates: {len(result['exercise_candidates'])}")
    print(f"Overall score: {result['combined_assessment']['overall_score']}/100")
    print(f"Is safe: {result['combined_assessment']['is_safe']}")

    return result


def cmd_all(args):
    """Run all tests"""
    check_config()

    print("\n" + "=" * 50)
    print("FULL INTEGRATION TEST")
    print("=" * 50)

    # Diet
    print("\n[1/4] Testing Diet Generator...")
    diet_candidates = cmd_diet(args)

    # Exercise
    print("\n[2/4] Testing Exercise Generator...")
    exercise_candidates = cmd_exercise(args)

    # Safeguard
    print("\n[3/4] Testing Safeguard...")
    assessment = cmd_safeguard(args)

    # Pipeline
    print("\n[4/4] Testing Full Pipeline...")
    result = cmd_pipeline(args)

    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETED")
    print("=" * 50)

    return {
        "diet": diet_candidates,
        "exercise": exercise_candidates,
        "safeguard": assessment,
        "pipeline": result
    }


def main():
    parser = argparse.ArgumentParser(
        description="kg_agents CLI - Health Plan Generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py all                         # Run full integration test
    python run.py diet --goal weight_loss     # Generate diet plans
    python run.py exercise --goal muscle_gain  # Generate exercise plans
    python run.py pipeline --no-filter        # Run pipeline without safety filter
        """
    )

    parser.add_argument(
        "--config", "-c",
        help="Path to config.json (default: ./config.json)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Diet command
    diet_parser = subparsers.add_parser("diet", help="Generate diet candidates")
    diet_parser.add_argument("--conditions", "-C", help="Medical conditions (comma-separated)")
    diet_parser.add_argument("--restrictions", "-R", help="Dietary restrictions (comma-separated)")
    diet_parser.add_argument("--goal", "-G", help="Diet goal")
    diet_parser.add_argument("--num", "-N", type=int, help="Number of candidates")

    # Exercise command
    exer_parser = subparsers.add_parser("exercise", help="Generate exercise candidates")
    exer_parser.add_argument("--conditions", "-C", help="Medical conditions (comma-separated)")
    exer_parser.add_argument("--goal", "-G", help="Exercise goal")
    exer_parser.add_argument("--num", "-N", type=int, help="Number of candidates")

    # Safeguard command
    safeguard_parser = subparsers.add_parser("safeguard", help="Run safety assessment")
    safeguard_parser.add_argument("--conditions", "-C", help="Medical conditions (comma-separated)")

    # Pipeline command
    pipeline_parser = subparsers.add_parser("pipeline", help="Run full health pipeline")
    pipeline_parser.add_argument("--conditions", "-C", help="Medical conditions (comma-separated)")
    pipeline_parser.add_argument("--restrictions", "-R", help="Dietary restrictions (comma-separated)")
    pipeline_parser.add_argument("--goal", "-G", help="Health goal")
    pipeline_parser.add_argument("--num", "-N", type=int, help="Number of candidates")
    pipeline_parser.add_argument("--no-filter", action="store_true", help="Don't filter by safety score")
    pipeline_parser.add_argument("--min-score", type=int, help="Minimum safety score")

    # All command
    subparsers.add_parser("all", help="Run full integration test")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Route to appropriate command
    commands = {
        "diet": cmd_diet,
        "exercise": cmd_exercise,
        "safeguard": cmd_safeguard,
        "pipeline": cmd_pipeline,
        "all": cmd_all
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
