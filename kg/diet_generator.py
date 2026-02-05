"""
Diet Candidate Generator Module
Generates personalized meal plan candidates based on user metadata and knowledge graph.

Phase 2: NL-to-Cypher Translation & Multi-Constraint Query Builder
Phase 3: LLM-based Diet Recommendation (No hardcoded food database)
"""
import json
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from neo4j import GraphDatabase
from openai import OpenAI
from pydantic import BaseModel, Field, validator
from enum import Enum

# ================= Configuration =================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

NEO4J_URI = config["neo4j"]["uri"]
NEO4J_AUTH = (config["neo4j"]["username"], config["neo4j"]["password"])
DEEPSEEK_API_KEY = config["deepseek"]["api_key"]
DEEPSEEK_BASE_URL = config["deepseek"]["base_url"]

driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


# ================= JSON Schema Definitions for LLM Output =================

class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACKS = "snacks"


class FoodItem(BaseModel):
    """A single food item in a meal"""
    food: str = Field(..., description="Name of the food dish")
    portion: str = Field(..., description="Portion size (e.g., '100g', '1碗', '2片')")
    calories: int = Field(..., description="Estimated calories per serving")
    protein: float = Field(..., description="Protein content in grams")
    carbs: float = Field(..., description="Carbohydrate content in grams")
    fat: float = Field(..., description="Fat content in grams")
    fiber: Optional[float] = Field(None, description="Fiber content in grams")
    reason: str = Field(..., description="Why this food is suitable for the user")


class MealPlanItem(BaseModel):
    """A complete meal with multiple food items"""
    meal_type: MealType = Field(..., description="Type of meal")
    items: List[FoodItem] = Field(..., description="Food items in this meal")
    total_calories: int = Field(..., description="Total calories for this meal")
    total_protein: float = Field(..., description="Total protein in grams")
    total_carbs: float = Field(..., description="Total carbohydrates in grams")
    total_fat: float = Field(..., description="Total fat in grams")


class MacroNutrients(BaseModel):
    """Daily macro nutrient summary"""
    protein: float = Field(..., description="Total protein in grams")
    carbs: float = Field(..., description="Total carbohydrates in grams")
    fat: float = Field(..., description="Total fat in grams")
    protein_ratio: float = Field(..., description="Protein calorie percentage (15-25% ideal)")
    carbs_ratio: float = Field(..., description="Carbohydrate calorie percentage (45-65% ideal)")
    fat_ratio: float = Field(..., description="Fat calorie percentage (20-35% ideal)")


class DietRecommendation(BaseModel):
    """Complete diet recommendation for one candidate"""
    id: int = Field(..., description="Candidate ID")
    meal_plan: Dict[str, List[FoodItem]] = Field(..., description="Full day meal plan")
    total_calories: int = Field(..., description="Total daily calories")
    calories_deviation: float = Field(..., description="Deviation from target calories (%)")
    macro_nutrients: MacroNutrients = Field(..., description="Macro nutrient summary")
    reasoning: str = Field(..., description="Overall reasoning for this recommendation")
    safety_notes: List[str] = Field(default_factory=list, description="Safety considerations")


class DietCandidatesResponse(BaseModel):
    """Response containing multiple diet candidates"""
    candidates: List[DietRecommendation] = Field(..., description="List of diet candidates")
    target_calories: int = Field(..., description="Target daily calories")
    user_conditions: List[str] = Field(..., description="User's health conditions considered")
    sampling_strategy: str = Field(..., description="Strategy used for generation")
    generation_notes: str = Field(..., description="Additional notes about generation")


# ================= Knowledge Graph Schema Reference =================
DISH_INGREDIENT_SCHEMA = """
    节点类型:
    - Dish: 菜品
    - Ingredient: 食材
    - Nutrient: 营养素
    - Disease: 疾病
    - Crowd: 人群

    关系类型:
    - CONTAINS_INGREDIENT: 菜品包含食材
    - CONTAINS_NUTRIENT: 食材包含营养素
    - SUITABLE_FOR: 适合疾病/人群
    - AVOID_FOR: 禁忌疾病/人群
    - HAS_CALORIE: 热量
    - HAS_PROTEIN: 蛋白质含量
    - HAS_CARBS: 碳水化合物含量
    - HAS_FAT: 脂肪含量
    - HAS_FIBER: 纤维含量
"""


# ================= System Prompt for LLM =================
DIET_GENERATION_SYSTEM_PROMPT = """你是一位专业的营养师和健康顾问。你的任务是根据用户的健康状况和目标，为他们制定个性化的饮食方案。

## 你的职责
1. 分析用户的健康状况（疾病、饮食限制等）
2. 根据营养学原理制定均衡的饮食计划
3. 确保食物选择符合用户的健康需求
4. 提供详细的营养素分析和安全建议

## 输出格式要求
你必须严格按照JSON格式输出饮食建议，JSON必须完整且有效。

## 营养学指导原则

### 每日营养分配
- 早餐: 25% 每日热量
- 午餐: 35% 每日热量
- 晚餐: 30% 每日热量
- 零食: 10% 每日热量

### 宏量营养素比例（健康成年人）
- 蛋白质: 15-25% 总热量
- 碳水化合物: 45-65% 总热量
- 脂肪: 20-35% 总热量

### 特殊人群注意事项
- 糖尿病患者: 控制碳水摄入，选择低GI食物
- 高血压患者: 低钠饮食（<2000mg钠）
- 高血脂患者: 减少饱和脂肪，增加膳食纤维
- 减肥人群: 热量缺口300-500kcal
- 增肌人群: 高蛋白饮食（1.6-2.2g/kg体重）

## 食物选择原则
1. 选择新鲜、天然的食材
2. 多样化搭配，确保营养均衡
3. 考虑季节和地域特点
4. 符合用户的口味偏好（如果已知）

## 格式说明
所有输出必须使用中文，包括：
- 食物名称
- 份量描述
- 推荐理由
- 安全提示

请生成符合用户需求的饮食方案，确保科学性和可操作性。
"""


# ================= LLM-based Diet Generation Functions =================

def build_diet_prompt(
    user_metadata: Dict,
    environment: Dict = None,
    user_requirement: Dict = None,
    candidate_id: int = 1
) -> str:
    """
    Build a detailed prompt for LLM to generate diet recommendations.

    Args:
        user_metadata: User health information
        environment: Weather/time context (optional)
        user_requirement: User preferences (optional)
        candidate_id: ID for this candidate (for differentiation)

    Returns:
        Formatted prompt string
    """
    # Extract user information
    age = user_metadata.get("age", 30)
    gender = user_metadata.get("gender", "male")
    height_cm = user_metadata.get("height_cm", 170)
    weight_kg = user_metadata.get("weight_kg", 70)
    bmi = user_metadata.get("bmi", 22)
    conditions = user_metadata.get("medical_conditions", [])
    restrictions = user_metadata.get("dietary_restrictions", [])
    fitness_level = user_metadata.get("fitness_level", "beginner")

    # Extract environment info
    season = None
    if environment:
        season = environment.get("time_context", {}).get("season", "spring")

    # Extract user requirements
    goal = "maintain"
    if user_requirement:
        goal = user_requirement.get("goal", "maintain")

    # Calculate target calories (simplified BMR formula)
    # Harris-Benedict equation
    if gender.lower() == "male":
        bmr = 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
    else:
        bmr = 447.593 + (9.247 * weight_kg) + (3.098 * height_cm) - (4.330 * age)

    # Activity multiplier
    activity_multipliers = {
        "sedentary": 1.2,
        "beginner": 1.375,
        "intermediate": 1.55,
        "advanced": 1.725
    }
    activity_mult = activity_multipliers.get(fitness_level, 1.2)

    # Goal adjustment
    if goal == "weight_loss":
        target_calories = int(bmr * activity_mult - 400)
    elif goal == "weight_gain":
        target_calories = int(bmr * activity_mult + 400)
    else:
        target_calories = int(bmr * activity_mult)

    # Build the detailed prompt
    prompt = f"""
## 用户信息

### 基本信息
- 年龄: {age}岁
- 性别: {gender}
- 身高: {height_cm}cm
- 体重: {weight_kg}kg
- BMI: {bmi}
- 健身水平: {fitness_level}

### 健康状况（需要特别考虑）: {', '.join(conditions) if conditions else '无'}
### 饮食限制: {', '.join(restrictions) if restrictions else '无'}

### 目标: {goal}
- 维持: 保持当前体重
- 减肥: 减少体重
- 增肌: 增加肌肉量

## 环境因素
- 季节: {season if season else '未知'}

## 计算参数
- 基础代谢率(BMR): {int(bmr)} kcal
- 活动系数: {activity_mult}
- 目标热量: {target_calories} kcal

## 任务要求
请为这位用户生成第{candidate_id}个饮食方案候选。

### 饮食分配（基于{target_calories} kcal目标）
- 早餐: {int(target_calories * 0.25)} kcal (25%)
- 午餐: {int(target_calories * 0.35)} kcal (35%)
- 晚餐: {int(target_calories * 0.30)} kcal (30%)
- 零食: {int(target_calories * 0.10)} kcal (10%)

### 特殊饮食要求
"""
    # Add disease-specific requirements
    if "diabetes" in [c.lower() for c in conditions]:
        prompt += "- 糖尿病: 选择低GI食物，控制碳水，控制总热量\n"
    if "hypertension" in [c.lower() for c in conditions]:
        prompt += "- 高血压: 低钠饮食，每日钠摄入<2000mg\n"
    if "hyperlipidemia" in [c.lower() for c in conditions]:
        prompt += "- 高血脂: 减少饱和脂肪，增加膳食纤维\n"
    if "low_sodium" in [r.lower() for r in restrictions]:
        prompt += "- 低钠饮食: 严格控制钠摄入\n"

    # Add goal-specific requirements
    if goal == "weight_loss":
        prompt += "- 减肥: 热量缺口300-500kcal，增加蔬菜和蛋白质\n"
    elif goal == "weight_gain":
        prompt += "- 增肌: 高蛋白饮食，增加健康脂肪\n"

    # Add season-specific suggestions
    if season == "summer":
        prompt += "- 夏季: 推荐清淡、解暑的食物，多摄入水分\n"
    elif season == "winter":
        prompt += "- 冬季: 推荐温热食物，适量增加热量\n"

    prompt += """
## 输出格式

请严格按照以下JSON格式输出（不要添加任何其他文字说明）：

{
    "id": 1,
    "meal_plan": {
        "breakfast": [
            {
                "food": "食物名称",
                "portion": "份量描述",
                "calories": 热量数值,
                "protein": 蛋白质克数,
                "carbs": 碳水克数,
                "fat": 脂肪克数,
                "fiber": 纤维克数（可选）,
                "reason": "推荐理由"
            }
        ],
        "lunch": [...],
        "dinner": [...],
        "snacks": [...]
    },
    "total_calories": 总热量,
    "calories_deviation": 偏差百分比,
    "macro_nutrients": {
        "protein": 蛋白质总量,
        "carbs": 碳水总量,
        "fat": 脂肪总量,
        "protein_ratio": 蛋白质供能比,
        "carbs_ratio": 碳水供能比,
        "fat_ratio": 脂肪供能比
    },
    "reasoning": "整体推荐理由",
    "safety_notes": ["安全提示1", "安全提示2"]
}

请确保：
1. JSON格式完整且有效
2. 所有营养数值合理准确
3. 食物搭配符合营养学原理
4. 考虑用户的健康状况和饮食限制
5. 每餐食物种类3-5种，保证多样性
"""
    return prompt


def generate_diet_candidate(
    user_metadata: Dict,
    environment: Dict = None,
    user_requirement: Dict = None,
    candidate_id: int = 1
) -> Optional[DietRecommendation]:
    """
    Generate a single diet recommendation candidate using LLM.

    Args:
        user_metadata: User health information
        environment: Weather/time context (optional)
        user_requirement: User preferences (optional)
        candidate_id: ID for this candidate

    Returns:
        DietRecommendation object or None if generation fails
    """
    prompt = build_diet_prompt(
        user_metadata, environment, user_requirement, candidate_id
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": DIET_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=None
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find JSON directly
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = content

        # Parse JSON
        data = json.loads(json_str)

        # Validate and create DietRecommendation
        return DietRecommendation(**data)

    except json.JSONDecodeError as e:
        print(f"[Diet Generation] JSON parsing error (candidate {candidate_id}): {e}")
        print(f"[Diet Generation] Raw content: {content[:500]}")
        return None
    except Exception as e:
        print(f"[Diet Generation] Error (candidate {candidate_id}): {e}")
        return None


def generate_diet_candidates_llm(
    user_metadata: Dict,
    environment: Dict = None,
    user_requirement: Dict = None,
    num_candidates: int = 3,
    sampling_strategy: str = "balanced"
) -> DietCandidatesResponse:
    """
    Generate multiple diet recommendation candidates using LLM.

    Args:
        user_metadata: User health information
        environment: Weather/time context (optional)
        user_requirement: User preferences (optional)
        num_candidates: Number of candidates to generate
        sampling_strategy: Strategy description for the response

    Returns:
        DietCandidatesResponse with multiple candidates
    """
    candidates = []
    conditions = user_metadata.get("medical_conditions", [])

    # Calculate target calories for notes
    age = user_metadata.get("age", 30)
    gender = user_metadata.get("gender", "male")
    height_cm = user_metadata.get("height_cm", 170)
    weight_kg = user_metadata.get("weight_kg", 70)
    fitness_level = user_metadata.get("fitness_level", "beginner")
    goal = user_requirement.get("goal", "maintain") if user_requirement else "maintain"

    if gender.lower() == "male":
        bmr = 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
    else:
        bmr = 447.593 + (9.247 * weight_kg) + (3.098 * height_cm) - (4.330 * age)

    activity_multipliers = {
        "sedentary": 1.2, "beginner": 1.375, "intermediate": 1.55, "advanced": 1.725
    }
    activity_mult = activity_multipliers.get(fitness_level, 1.2)

    if goal == "weight_loss":
        target_calories = int(bmr * activity_mult - 400)
    elif goal == "weight_gain":
        target_calories = int(bmr * activity_mult + 400)
    else:
        target_calories = int(bmr * activity_mult)

    # Generate candidates with different prompts
    for i in range(num_candidates):
        # Vary the prompt slightly for diversity
        candidate_metadata = user_metadata.copy()
        if i > 0:
            # Add variety hints for subsequent candidates
            variety_hints = ["注重蔬菜摄入", "增加水果种类", "多样化蛋白质来源"]
            candidate_metadata["_variety_hint"] = variety_hints[i % len(variety_hints)]

        candidate = generate_diet_candidate(
            candidate_metadata,
            environment,
            user_requirement,
            candidate_id=i+1
        )
        if candidate:
            candidates.append(candidate)

    # Sort by calories deviation (best match first)
    candidates.sort(key=lambda x: abs(x.calories_deviation))

    # Build generation notes
    generation_notes = (
        f"基于用户{len(conditions)}个健康状况生成，"
        f"目标热量{target_calories}kcal，"
        f"采用{sampling_strategy}策略。"
    )

    return DietCandidatesResponse(
        candidates=candidates,
        target_calories=target_calories,
        user_conditions=conditions,
        sampling_strategy=sampling_strategy,
        generation_notes=generation_notes
    )


# ================= Phase 2: KG Context Functions (Optional for Enhancement) =================

def query_kg_for_dietary_knowledge(user_metadata: Dict) -> Dict:
    """
    Query knowledge graph for dietary recommendations context.
    This provides additional context to enhance LLM generation.

    Returns:
        Dict with dietary recommendations from KG
    """
    with driver.session() as session:
        diseases = user_metadata.get("medical_conditions", [])
        restrictions = user_metadata.get("dietary_restrictions", [])

        kg_context = {
            "disease_recommendations": [],
            "food_restrictions": [],
            "nutrient_advice": []
        }

        # Query diseases and related food advice
        for disease in diseases:
            result = session.run("""
                MATCH (d:Disease {name: $disease})-[:HAS_DIET]->(diet:Diet)
                OPTIONAL MATCH (diet)-[:RECOMMENDS_FOOD]->(food:Food)
                OPTIONAL MATCH (diet)-[:CONTAINS_NUTRIENT]->(nutrient:Nutrient)
                RETURN diet.name as diet_name, collect(DISTINCT food.name) as foods,
                       collect(DISTINCT nutrient.name) as nutrients
                LIMIT 5
            """, disease=disease)

            for rec in result:
                kg_context["disease_recommendations"].append({
                    "diet_type": rec["diet_name"],
                    "recommended_foods": rec["foods"],
                    "key_nutrients": rec["nutrients"]
                })

        # Query restrictions
        for restriction in restrictions:
            result = session.run("""
                MATCH (r:DietaryRestriction {name: $restriction})
                OPTIONAL MATCH (r)-[:AVOIDS_FOOD]->(food:Food)
                RETURN collect(DISTINCT food.name) as avoid_foods
            """, restriction=restriction)

            for rec in result:
                kg_context["food_restrictions"].extend(rec["avoid_foods"])

        return kg_context


def build_kg_enhanced_prompt(user_metadata: Dict, kg_context: Dict = None) -> str:
    """
    Build diet prompt enhanced with knowledge graph context.

    Args:
        user_metadata: User health information
        kg_context: Knowledge graph context (optional)

    Returns:
        Enhanced prompt string
    """
    base_prompt = build_diet_prompt(user_metadata)

    if not kg_context:
        return base_prompt

    # Add KG context if available
    if kg_context.get("disease_recommendations"):
        base_prompt += "\n## 知识图谱饮食建议\n"
        for rec in kg_context["disease_recommendations"]:
            base_prompt += f"- {rec['diet_type']}饮食建议: {', '.join(rec['recommended_foods'])}\n"
            if rec['key_nutrients']:
                base_prompt += f"  关键营养素: {', '.join(rec['key_nutrients'])}\n"

    if kg_context.get("food_restrictions"):
        base_prompt += f"\n## 需避免的食物\n根据知识图谱，应避免: {', '.join(set(kg_context['food_restrictions']))}\n"

    return base_prompt


# ================= Main Interface Function =================

def generate_diet_candidates(
    user_metadata: Dict,
    environment: Dict = None,
    user_requirement: Dict = None,
    num_candidates: int = 3,
    sampling_strategy: str = "balanced",
    use_kg_enhancement: bool = False
) -> Dict[str, Any]:
    """
    Main function to generate diet plan candidates.

    This is the primary entry point for diet recommendation generation.
    Uses LLM to generate personalized meal plans based on user metadata.

    Args:
        user_metadata: User health information (age, gender, height, weight, conditions, etc.)
        environment: Weather/time context (optional)
        user_requirement: User preferences (goal: weight_loss/maintain/weight_gain)
        num_candidates: Number of candidates to generate (default: 3)
        sampling_strategy: Sampling strategy (balanced/calorie_optimal/protein_priority)
        use_kg_enhancement: Whether to enhance with KG knowledge (default: False)

    Returns:
        Dict with 'candidates' list containing meal plans and metadata
    """
    # Optional KG enhancement
    kg_context = None
    if use_kg_enhancement:
        try:
            kg_context = query_kg_for_dietary_knowledge(user_metadata)
        except Exception as e:
            print(f"[Diet Generation] KG context unavailable: {e}")

    # Generate candidates using LLM
    response = generate_diet_candidates_llm(
        user_metadata=user_metadata,
        environment=environment,
        user_requirement=user_requirement,
        num_candidates=num_candidates,
        sampling_strategy=sampling_strategy
    )

    # Convert to dict for compatibility
    return {
        "candidates": [c.model_dump() for c in response.candidates],
        "target_calories": response.target_calories,
        "user_conditions": response.user_conditions,
        "sampling_strategy": response.sampling_strategy,
        "generation_notes": response.generation_notes,
        "kg_enhanced": use_kg_enhancement and kg_context is not None
    }


# ================= Deprecated Functions (保留仅作为参考) =================
# 注意: 以下函数已废弃，不再使用硬编码的FOOD_DATABASE
# 所有饮食推荐现在通过LLM动态生成

def generate_cypher_for_query(user_metadata: Dict, user_requirement: Dict = None) -> str:
    """
    [DEPRECATED] Generate Cypher query from natural language requirements using LLM.
    This function is kept for reference but is no longer used in the main flow.

    Args:
        user_metadata: User health information
        user_requirement: User preferences

    Returns:
        Cypher query string (for reference only)
    """
    print("[Warning] generate_cypher_for_query is deprecated. Use generate_diet_candidates instead.")
    conditions = user_metadata.get("medical_conditions", [])
    goal = user_requirement.get("goal", "maintain") if user_requirement else "maintain"

    # Build context for LLM
    context = f"""
    用户条件:
    - 疾病: {conditions}
    - 目标: {goal}

    任务: 生成饮食推荐（已通过LLM动态生成，此函数仅作参考）
    """
    return context


if __name__ == "__main__":
    # Test the new LLM-based diet generation module
    test_metadata = {
        "age": 35,
        "gender": "male",
        "height_cm": 175,
        "weight_kg": 70,
        "bmi": 22.9,
        "medical_conditions": ["diabetes"],
        "dietary_restrictions": ["low_sodium"],
        "fitness_level": "intermediate"
    }

    test_environment = {
        "weather": {"condition": "clear", "temperature_c": 25},
        "time_context": {"season": "summer", "time_of_day": "morning"}
    }

    test_requirement = {"goal": "weight_loss"}

    print("=== 测试 LLM-based Diet Generation ===\n")
    print("用户信息:")
    print(f"  - 年龄: {test_metadata['age']}岁")
    print(f"  - 性别: {test_metadata['gender']}")
    print(f"  - 健康状况: {', '.join(test_metadata['medical_conditions'])}")
    print(f"  - 饮食限制: {', '.join(test_metadata['dietary_restrictions'])}")
    print(f"  - 健身水平: {test_metadata['fitness_level']}")
    print(f"  - 目标: {test_requirement['goal']}")
    print()

    # 测试生成饮食推荐
    print("1. 生成饮食推荐候选...")
    result = generate_diet_candidates(
        test_metadata,
        environment=test_environment,
        user_requirement=test_requirement,
        num_candidates=2,
        sampling_strategy="balanced"
    )

    print(f"\n目标热量: {result['target_calories']} kcal")
    print(f"采样策略: {result['sampling_strategy']}")
    print(f"生成说明: {result['generation_notes']}")
    print(f"使用KG增强: {result['kg_enhanced']}")
    print()

    for candidate in result["candidates"][:2]:
        print(f"候选 {candidate['id']}:")
        print(f"  总热量: {candidate['total_calories']} kcal (偏差: {candidate['calories_deviation']}%)")
        print(f"  整体理由: {candidate['reasoning'][:100]}...")

        macros = candidate['macro_nutrients']
        print(f"  营养素: 蛋白{macros['protein']}g, 碳水{macros['carbs']}g, 脂肪{macros['fat']}g")
        print(f"  供能比: 蛋白{macros['protein_ratio']}%, 碳水{macros['carbs_ratio']}%, 脂肪{macros['fat_ratio']}%")

        print("\n  餐计划:")
        for meal_type, items in candidate['meal_plan'].items():
            meal_names = [item['food'] for item in items]
            print(f"    {meal_type}: {', '.join(meal_names)}")

        if candidate['safety_notes']:
            print(f"\n  安全提示:")
            for note in candidate['safety_notes']:
                print(f"    - {note}")
        print()

    print("=== 测试完成 ===")
