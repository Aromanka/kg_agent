"""
Diet Plan Parser
Parses and expands LLM-generated base diet plans into multiple portion variants.

Strategy: Generate "Lite", "Standard", "Plus" variants by applying
scaling rules based on portion unit type.
"""
from typing import List, Dict, Any
from .models import BaseFoodItem


class DietPlanParser:
    """
    Diet plan parser and expander.

    Takes a base plan from LLM and expands it into multiple variants
    (Lite, Standard, Plus) based on deterministic scaling rules.
    """

    def __init__(self):
        # Scaling factors for each variant
        self.variants = {
            "Lite": 0.8,       # 80% of base portion
            "Standard": 1.0,    # 100% of base portion
            "Plus": 1.2        # 120% of base portion
        }

        # Unit-specific adjustments for discrete quantities
        self.unit_adjustments = {
            # Continuous units: direct multiplication
            "gram": None,
            "ml": None,
            # Discrete units: half-unit steps
            "piece": 0.5,
            "slice": 1.0,
            "cup": 0.5,
            "bowl": 0.5,
            # Spoon: no adjustment (keep exact)
            "spoon": 0.0
        }

    def expand_plan(
        self,
        base_items: List[BaseFoodItem],
        variants: List[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Expand a base plan into multiple variants.

        Args:
            base_items: List of BaseFoodItem from LLM
            variants: Which variants to generate (default: Lite, Standard, Plus)

        Returns:
            Dict mapping variant name to expanded plan items
            {
                "Lite": [...items with scaled portions],
                "Standard": [...items with original portions],
                "Plus": [...items with increased portions]
            }
        """
        if variants is None:
            variants = ["Lite", "Standard", "Plus"]

        result = {}

        for variant_name in variants:
            scale_factor = self.variants.get(variant_name, 1.0)
            expanded_items = []

            for item in base_items:
                new_item = self._scale_item(item, scale_factor)
                new_item["_variant"] = variant_name
                expanded_items.append(new_item)

            result[variant_name] = expanded_items

        return result

    def _scale_item(
        self,
        item: BaseFoodItem,
        scale_factor: float
    ) -> Dict[str, Any]:
        """
        Scale a single food item according to rules.

        Args:
            item: BaseFoodItem to scale
            scale_factor: Multiplier (e.g., 0.8, 1.0, 1.2)

        Returns:
            Dict with scaled portion_number and recalculated calories
        """
        unit = item.portion_unit
        original_num = item.portion_number

        # Support both formats
        if hasattr(item, 'total_calories') and item.total_calories and item.total_calories > 0:
            # New format: LLM outputs total_calories for the whole portion
            original_total = item.total_calories
        elif hasattr(item, 'calories_per_unit') and item.calories_per_unit:
            # Old format: calculate total from calories_per_unit
            original_total = item.calories_per_unit * original_num
        else:
            original_total = 0

        # Calculate scaled portion number
        scaled_num = self._calculate_scaled_number(original_num, unit, scale_factor)

        # Calculate total calories: scale proportionally to portion change
        if original_num > 0:
            total_calories = round(original_total * (scaled_num / original_num), 1)
            calories_per_unit = round(original_total / original_num, 2)
        else:
            total_calories = original_total
            calories_per_unit = original_total

        return {
            "food_name": item.food_name,
            "portion_number": scaled_num,
            "portion_unit": unit,
            "calories_per_unit": calories_per_unit,
            "total_calories": total_calories
        }

    def _calculate_scaled_number(
        self,
        original: float,
        unit: str,
        scale_factor: float
    ) -> float:
        """
        Calculate scaled portion number based on unit type.

        Continuous units (gram, ml): direct multiplication
        Discrete units (piece, slice): step-wise adjustment
        """
        if unit in ["gram", "ml"]:
            # Continuous: direct multiplication, round to 1 decimal
            return round(original * scale_factor, 1)

        elif unit in ["piece", "slice", "cup", "bowl"]:
            # Discrete: calculate offset, then add
            adjustment = self.unit_adjustments.get(unit, 0.5)

            if scale_factor < 1.0:
                # Lite: reduce
                new_num = original - adjustment
                return max(0.5, round(new_num, 1))
            elif scale_factor > 1.0:
                # Plus: increase
                new_num = original + adjustment
                return round(new_num, 1)
            else:
                # Standard: keep original
                return original

        elif unit == "spoon":
            # Spoon: keep exact (usually small amounts)
            return original

        else:
            # Unknown unit: fallback to direct multiplication
            return round(original * scale_factor, 1)

    def expand_single_item(
        self,
        item: BaseFoodItem
    ) -> Dict[str, Dict[str, Any]]:
        """
        Convenience: Expand a single item into all variants.

        Returns:
            Dict mapping variant name to scaled item dict
        """
        return self.expand_plan([item])


# Convenience function
def expand_diet_plan(
    base_items: List[BaseFoodItem]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Quick helper to expand a diet plan.

    Args:
        base_items: List of BaseFoodItem from LLM

    Returns:
        Dict with "Lite", "Standard", "Plus" variants
    """
    parser = DietPlanParser()
    return parser.expand_plan(base_items)
