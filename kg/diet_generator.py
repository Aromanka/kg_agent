"""
Diet Candidate Generator Module
Generates personalized meal plan candidates based on user metadata and knowledge graph.

Phase 2: NL-to-Cypher Translation & Multi-Constraint Query Builder
"""
import json
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from neo4j import GraphDatabase
from openai import OpenAI

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


# ================= Extended Food Database (Sample 100+ foods) =================
FOOD_DATABASE = {
    "breakfast": [
        {"name": "燕麦粥", "category": "grains", "calories": 150, "protein": 5, "carbs": 27, "fat": 3, "fiber": 4, "sodium": 0, "suitable_for": ["糖尿病", "高血压", "高血脂", "减肥"]},
        {"name": "全麦面包", "category": "grains", "calories": 80, "protein": 4, "carbs": 14, "fat": 1, "fiber": 2, "sodium": 150, "suitable_for": ["糖尿病", "高血脂", "减肥"]},
        {"name": "鸡蛋", "category": "protein", "calories": 70, "protein": 6, "carbs": 0, "fat": 5, "fiber": 0, "sodium": 70, "suitable_for": ["健康人群", "增肌"]},
        {"name": "牛奶", "category": "dairy", "calories": 120, "protein": 8, "carbs": 12, "fat": 5, "fiber": 0, "sodium": 100, "suitable_for": ["健康人群", "骨质疏松"]},
        {"name": "豆浆", "category": "dairy", "capacity": 250, "calories": 80, "protein": 8, "carbs": 4, "fat": 4, "fiber": 0, "sodium": 10, "suitable_for": ["乳糖不耐受", "素食", "高血脂"]},
        {"name": "玉米", "category": "grains", "calories": 90, "protein": 3, "carbs": 19, "fat": 1, "fiber": 2, "sodium": 0, "suitable_for": ["健康人群", "便秘"]},
        {"name": "紫薯", "category": "grains", "calories": 120, "protein": 2, "carbs": 28, "fat": 0, "fiber": 3, "sodium": 10, "suitable_for": ["减肥", "抗氧化"]},
        {"name": "小米粥", "category": "grains", "calories": 100, "protein": 3, "carbs": 22, "fat": 1, "fiber": 1, "sodium": 5, "suitable_for": ["胃病", "产后恢复"]},
        {"name": "荞麦面", "category": "grains", "calories": 110, "protein": 5, "carbs": 20, "fat": 1, "fiber": 3, "sodium": 0, "suitable_for": ["糖尿病", "高血脂"]},
        {"name": "低脂酸奶", "category": "dairy", "calories": 100, "protein": 10, "carbs": 8, "fat": 2, "fiber": 0, "sodium": 80, "suitable_for": ["减肥", "肠道健康"]},
        {"name": "香蕉", "category": "fruit", "calories": 90, "protein": 1, "carbs": 23, "fat": 0, "fiber": 3, "sodium": 1, "suitable_for": ["运动前", "钾补充"]},
        {"name": "苹果", "category": "fruit", "calories": 52, "protein": 0, "carbs": 14, "fat": 0, "fiber": 2, "sodium": 1, "suitable_for": ["减肥", "便秘", "抗氧化"]},
        {"name": "坚果混合", "category": "nuts", "calories": 170, "protein": 5, "carbs": 6, "fat": 15, "fiber": 2, "sodium": 5, "suitable_for": ["健康零食", "脑力工作者"]},
        {"name": "西兰花", "category": "vegetable", "calories": 35, "protein": 3, "carbs": 7, "fat": 0, "fiber": 3, "sodium": 30, "suitable_for": ["抗癌", "维生素C补充"]},
        {"name": "菠菜", "category": "vegetable", "calories": 23, "protein": 3, "carbs": 4, "fat": 0, "fiber": 2, "sodium": 79, "suitable_for": ["贫血", "骨质疏松"]},
    ],
    "lunch": [
        {"name": "糙米饭", "category": "grains", "capacity": 150, "calories": 180, "protein": 4, "carbs": 38, "fat": 2, "fiber": 3, "sodium": 5, "suitable_for": ["糖尿病", "减肥", "高血脂"]},
        {"name": "西兰花炒鸡胸肉", "category": "protein", "capacity": 200, "calories": 280, "protein": 35, "carbs": 10, "fat": 10, "fiber": 4, "sodium": 300, "suitable_for": ["减肥", "增肌", "高血脂"]},
        {"name": "清蒸鱼", "category": "protein", "capacity": 150, "calories": 150, "protein": 25, "carbs": 0, "fat": 5, "fiber": 0, "sodium": 100, "suitable_for": ["高血压", "孕妇", "脑健康"]},
        {"name": "凉拌黄瓜", "category": "vegetable", "capacity": 100, "calories": 16, "protein": 1, "carbs": 4, "fat": 0, "fiber": 1, "sodium": 2, "suitable_for": ["减肥", "清热解毒"]},
        {"name": "番茄炒蛋", "category": "protein", "capacity": 150, "calories": 180, "protein": 12, "carbs": 8, "fat": 12, "fiber": 1, "sodium": 200, "suitable_for": ["健康人群", "视力保护"]},
        {"name": "豆腐汤", "category": "protein", "capacity": 300, "calories": 120, "protein": 12, "carbs": 4, "fat": 6, "fiber": 0, "sodium": 300, "suitable_for": ["素食", "骨质疏松"]},
        {"name": "蒸南瓜", "category": "vegetable", "capacity": 150, "calories": 50, "protein": 1, "carbs": 12, "fat": 0, "fiber": 2, "sodium": 5, "suitable_for": ["减肥", "糖尿病"]},
        {"name": "牛肉炒芹菜", "category": "protein", "capacity": 150, "calories": 200, "protein": 25, "carbs": 5, "fat": 10, "fiber": 2, "sodium": 250, "suitable_for": ["贫血", "增肌"]},
        {"name": "虾仁炒西兰花", "category": "protein", "capacity": 150, "calories": 160, "protein": 20, "carbs": 6, "fat": 6, "fiber": 3, "sodium": 200, "suitable_for": ["减肥", "高血脂"]},
        {"name": "藜麦沙拉", "category": "grains", "capacity": 150, "calories": 180, "protein": 7, "carbs": 30, "fat": 4, "fiber": 5, "sodium": 100, "suitable_for": ["减肥", "素食", "健身"]},
        {"name": "烤三文鱼", "category": "protein", "capacity": 150, "calories": 250, "protein": 30, "carbs": 0, "fat": 14, "fiber": 0, "sodium": 150, "suitable_for": ["脑健康", "抗炎", "心血管健康"]},
        {"name": "香菇青菜", "category": "vegetable", "capacity": 150, "calories": 50, "protein": 4, "carbs": 8, "fat": 0, "fiber": 3, "sodium": 200, "suitable_for": ["免疫力", "抗癌"]},
        {"name": "蒜蓉炒菠菜", "category": "vegetable", "capacity": 150, "calories": 60, "protein": 5, "carbs": 6, "fat": 2, "fiber": 3, "sodium": 150, "suitable_for": ["贫血", "骨质疏松"]},
        {"name": "红烧豆腐", "category": "protein", "capacity": 150, "calories": 180, "protein": 15, "carbs": 10, "fat": 10, "fiber": 2, "sodium": 400, "suitable_for": ["素食", "增肌"]},
        {"name": "鸡胸肉沙拉", "category": "protein", "capacity": 200, "calories": 250, "protein": 35, "carbs": 8, "fat": 10, "fiber": 4, "sodium": 200, "suitable_for": ["减肥", "增肌"]},
    ],
    "dinner": [
        {"name": "杂粮粥", "category": "grains", "capacity": 250, "calories": 150, "protein": 4, "carbs": 32, "fat": 1, "fiber": 3, "sodium": 5, "suitable_for": ["减肥", "胃病", "糖尿病"]},
        {"name": "清炒时蔬", "category": "vegetable", "capacity": 200, "calories": 60, "protein": 3, "carbs": 10, "fat": 1, "fiber": 4, "sodium": 150, "suitable_for": ["减肥", "便秘", "高血脂"]},
        {"name": "蒸蛋羹", "category": "protein", "capacity": 100, "calories": 80, "protein": 7, "carbs": 1, "fat": 5, "fiber": 0, "sodium": 100, "suitable_for": ["儿童", "老人", "术后恢复"]},
        {"name": "红烧鱼块", "category": "protein", "capacity": 150, "calories": 200, "protein": 25, "carbs": 8, "fat": 8, "fiber": 0, "sodium": 300, "suitable_for": ["蛋白质补充"]},
        {"name": "木耳炒肉片", "category": "protein", "capacity": 150, "calories": 180, "protein": 15, "carbs": 10, "fat": 10, "fiber": 4, "sodium": 200, "suitable_for": ["补血", "降血脂"]},
        {"name": "冬瓜排骨汤", "category": "protein", "capacity": 300, "calories": 150, "protein": 12, "carbs": 5, "fat": 8, "fiber": 1, "sodium": 200, "suitable_for": ["利尿消肿", "清热"]},
        {"name": "蒜蓉西兰花", "category": "vegetable", "capacity": 150, "calories": 50, "protein": 5, "carbs": 8, "fat": 1, "fiber": 4, "sodium": 100, "suitable_for": ["抗癌", "维生素C补充"]},
        {"name": "烤鸡腿(去皮)", "category": "protein", "capacity": 150, "calories": 180, "protein": 30, "carbs": 0, "fat": 6, "fiber": 0, "sodium": 200, "suitable_for": ["增肌", "减肥"]},
        {"name": "糙米饭团", "category": "grains", "capacity": 100, "calories": 150, "protein": 3, "carbs": 32, "fat": 1, "fiber": 2, "sodium": 100, "suitable_for": ["减肥", "糖尿病"]},
        {"name": "鲈鱼清蒸", "category": "protein", "capacity": 150, "calories": 140, "protein": 25, "carbs": 0, "fat": 4, "fiber": 0, "sodium": 100, "suitable_for": ["高血压", "孕妇", "脑健康"]},
        {"name": "蔬菜豆腐煲", "category": "protein", "capacity": 250, "calories": 150, "protein": 12, "carbs": 12, "fat": 6, "fiber": 4, "sodium": 250, "suitable_for": ["素食", "减肥", "便秘"]},
        {"name": "荞麦面条", "category": "grains", "capacity": 150, "calories": 160, "protein": 6, "carbs": 30, "fat": 2, "fiber": 4, "sodium": 0, "suitable_for": ["糖尿病", "高血脂", "减肥"]},
        {"name": "芦笋炒虾仁", "category": "protein", "capacity": 150, "calories": 150, "protein": 20, "carbs": 4, "fat": 5, "fiber": 2, "sodium": 150, "suitable_for": ["减肥", "抗癌"]},
        {"name": "紫菜蛋花汤", "category": "soup", "capacity": 300, "calories": 60, "protein": 6, "carbs": 3, "fat": 2, "fiber": 1, "sodium": 300, "suitable_for": ["碘补充", "减肥"]},
        {"name": "燕麦牛奶", "category": "drink", "capacity": 250, "calories": 200, "protein": 10, "carbs": 30, "fat": 5, "fiber": 4, "sodium": 100, "suitable_for": ["减肥", "睡眠"]},
    ],
    "snacks": [
        {"name": "原味坚果", "category": "nuts", "capacity": 30, "calories": 180, "protein": 6, "carbs": 6, "fat": 16, "fiber": 3, "sodium": 5, "suitable_for": ["健康零食", "脑力工作者"]},
        {"name": "无糖酸奶", "category": "dairy", "capacity": 150, "calories": 90, "protein": 12, "carbs": 6, "fiber": 0, "fat": 2, "sodium": 80, "suitable_for": ["减肥", "肠道健康"]},
        {"name": "水果沙拉", "category": "fruit", "capacity": 200, "calories": 100, "protein": 1, "carbs": 25, "fat": 0, "fiber": 3, "sodium": 5, "suitable_for": ["减肥", "维生素补充"]},
        {"name": "黄瓜条", "category": "vegetable", "capacity": 100, "calories": 16, "protein": 1, "carbs": 4, "fat": 0, "fiber": 1, "sodium": 2, "suitable_for": ["减肥", "补水"]},
        {"name": "小番茄", "category": "fruit", "capacity": 100, "calories": 18, "protein": 1, "carbs": 4, "fat": 0, "fiber": 1, "sodium": 5, "suitable_for": ["减肥", "抗氧化"]},
        {"name": "魔芋果冻", "category": "snack", "capacity": 100, "calories": 10, "protein": 0, "carbs": 3, "fat": 0, "fiber": 2, "sodium": 20, "suitable_for": ["减肥", "糖尿病"]},
        {"name": "水煮毛豆", "category": "vegetable", "capacity": 100, "calories": 120, "protein": 12, "carbs": 10, "fat": 5, "fiber": 5, "sodium": 100, "suitable_for": ["蛋白质补充", "减肥"]},
        {"name": "鸡蛋白", "category": "protein", "capacity": 100, "calories": 50, "protein": 11, "carbs": 1, "fat": 0, "fiber": 0, "sodium": 150, "suitable_for": ["减肥", "增肌"]},
        {"name": "蓝莓", "category": "fruit", "capacity": 100, "calories": 57, "protein": 1, "carbs": 14, "fat": 0, "fiber": 2, "sodium": 1, "suitable_for": ["抗氧化", "脑健康", "视力保护"]},
        {"name": "即食海带", "category": "vegetable", "capacity": 50, "calories": 30, "protein": 2, "carbs": 5, "fat": 0, "fiber": 3, "sodium": 300, "suitable_for": ["碘补充", "减肥"]},
    ]
}


# ================= Knowledge Graph Schema =================
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


# ================= Core Functions =================

def init_food_database_in_kg():
    """Initialize food entities with nutritional attributes in Neo4j"""
    with driver.session() as session:
        # Create indexes
        session.run("CREATE FULLTEXT INDEX food_search_idx IF NOT EXISTS FOR (n:Food) ON EACH [n.name]")
        session.run("CREATE INDEX food_name_idx IF NOT EXISTS FOR (n:Food) ON (n.name)")

        # Import all foods from database
        for meal_type, foods in FOOD_DATABASE.items():
            for food in foods:
                session.run("""
                    MERGE (f:Food {name: $name})
                    SET f.category = $category,
                        f.calories = $calories,
                        f.protein = $protein,
                        f.carbs = $carbs,
                        f.fat = $fat,
                        f.fiber = $fiber,
                        f.sodium = $sodium,
                        f.meal_type = $meal_type,
                        f.portion = $portion
                    WITH f
                    UNWIND $suitable_for AS condition
                    MERGE (c:Crowd {name: condition})
                    MERGE (f)-[:SUITABLE_FOR]->(c)
                """,
                    name=food["name"],
                    category=food["category"],
                    calories=food["calories"],
                    protein=food["protein"],
                    carbs=food["carbs"],
                    fat=food["fat"],
                    fiber=food["fiber"],
                    sodium=food["sodium"],
                    meal_type=meal_type,
                    portion=food.get("capacity", 100),
                    suitable_for=food["suitable_for"]
                )

        print(f"已导入 {sum(len(f) for f in FOOD_DATABASE.values())} 个食物实体到知识图谱")


def query_suitable_foods(conditions: List[str], meal_type: str, max_calories: int = None) -> List[Dict]:
    """Query suitable foods from knowledge graph based on conditions"""
    with driver.session() as session:
        query = """
            MATCH (f:Food)-[:SUITABLE_FOR]->(c:Crowd)
            WHERE c.name IN $conditions AND f.meal_type = $meal_type
            WITH f, c.name as condition
            RETURN f.name as name, f.category as category, f.calories as calories,
                   f.protein as protein, f.carbs as carbs, f.fat as fat,
                   f.fiber as fiber, f.sodium as sodium, f.portion as portion
        """
        result = session.run(query, conditions=conditions, meal_type=meal_type)

        foods = []
        for rec in result:
            food = dict(rec)
            if max_calories and food["calories"] > max_calories:
                continue
            foods.append(food)

        return foods


# ================= Phase 2: NL-to-Cypher Translation =================

CYPHER_SYSTEM_PROMPT = """你是一个专业的Neo4j Cypher查询专家。你的任务是将用户的自然语言需求转换为准确的Cypher查询语句。

## 知识图谱Schema
节点类型:
- Food: 食物/菜品 (属性: name, category, calories, protein, carbs, fat, fiber, sodium, meal_type, portion)
- Crowd: 人群/疾病/症状 (属性: name)
- Nutrient: 营养素 (属性: name)

关系类型:
- SUITABLE_FOR: 食物适合某人群/疾病
- AVOID_FOR: 食物禁忌某人群/疾病
- CONTAINS_NUTRIENT: 食物包含某营养素
- HAS_RISK: 食物有某风险

## 输出格式要求
1. 只输出Cypher查询语句，不要解释
2. 使用参数化查询 ($variable)
3. 支持的查询模式:
   - 按疾病查询: MATCH (f:Food)-[:SUITABLE_FOR]->(:Crowd {name: $disease})
   - 按热量范围: WHERE f.calories >= $min_cal AND f.calories <= $max_cal
   - 按营养素: MATCH (f:Food)-[:CONTAINS_NUTRIENT]->(:Nutrient {name: $nutrient})
   - 按餐类型: WHERE f.meal_type = $meal_type
   - 复合条件: 使用AND连接多个条件

## 示例
输入: 糖尿病患者适合吃的早餐
输出:
```cypher
MATCH (f:Food)-[:SUITABLE_FOR]->(c:Crowd)
WHERE c.name = '糖尿病' AND f.meal_type = 'breakfast'
RETURN f.name as name, f.category as category, f.calories as calories,
       f.protein as protein, f.carbs as carbs, f.fat as fat
LIMIT 20
```

输入: 找低脂高蛋白的食物，减肥用
输出:
```cypher
MATCH (f:Food)
WHERE f.fat < 10 AND f.protein > 15
RETURN f.name, f.calories, f.protein, f.carbs, f.fat
ORDER BY f.protein DESC
LIMIT 30
```
"""


def nl_to_cypher(user_question: str, user_metadata: Dict = None) -> str:
    """
    将自然语言转换为Cypher查询

    Args:
        user_question: 用户自然语言需求
        user_metadata: 用户健康信息（可选，用于补充上下文）

    Returns:
        Cypher查询语句
    """
    # 构建上下文
    context_parts = [user_question]

    if user_metadata:
        conditions = user_metadata.get("medical_conditions", [])
        restrictions = user_metadata.get("dietary_restrictions", [])
        goal = user_metadata.get("goal", "maintain")

        if conditions:
            context_parts.append(f"\n用户疾病: {', '.join(conditions)}")
        if restrictions:
            context_parts.append(f"\n饮食限制: {', '.join(restrictions)}")
        context_parts.append(f"\n目标: {goal}")

    context = "\n".join(context_parts)

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": CYPHER_SYSTEM_PROMPT},
                {"role": "user", "content": f"请将以下需求转换为Cypher查询:\n{context}"}
            ],
            temperature=0.1
        )

        result = resp.choices[0].message.content.strip()

        # 提取Cypher代码块
        cypher_match = re.search(r'```cypher?\n(.*?)\n```', result, re.DOTALL)
        if cypher_match:
            return cypher_match.group(1).strip()

        # 如果没有代码块，尝试直接返回
        if result.startswith("MATCH") or result.startswith("match"):
            return result

        return None

    except Exception as e:
        print(f"[NL-to-Cypher] Error: {e}")
        return None


def execute_cypher_query(cypher_query: str, parameters: Dict = None) -> List[Dict]:
    """执行Cypher查询并返回结果"""
    with driver.session() as session:
        try:
            result = session.run(cypher_query, parameters or {})
            records = []
            for rec in result:
                records.append(dict(rec))
            return records
        except Exception as e:
            print(f"[Cypher Execute] Error: {e}")
            print(f"Query: {cypher_query}")
            return []


# ================= Phase 2: Multi-Constraint Query Builder =================

class MultiConstraintQueryBuilder:
    """
    多约束查询构建器
    支持组合: 疾病约束、热量约束、营养素约束、餐类型约束、偏好约束
    """

    def __init__(self):
        self.constraints = []
        self.parameters = {}

    def add_disease_constraint(self, diseases: List[str]) -> 'MultiConstraintQueryBuilder':
        """添加疾病约束 - 查找适合该疾病的食物"""
        if not diseases:
            return self

        # 疾病名称标准化映射
        disease_map = {
            "diabetes": "糖尿病",
            "糖尿病": "糖尿病",
            "hypertension": "高血压",
            "高血压": "高血压",
            "hyperlipidemia": "高血脂",
            "高血脂": "高血脂",
            "obesity": "肥胖",
            "肥胖": "肥胖",
            "anemia": "贫血",
            "贫血": "贫血",
            "osteoporosis": "骨质疏松",
            "骨质疏松": "骨质疏松",
        }

        standardized = []
        for d in diseases:
            standardized.append(disease_map.get(d.lower(), d))

        self.constraints.append("""
            EXISTS {
                MATCH (f:Food)-[:SUITABLE_FOR]->(c:Crowd)
                WHERE c.name IN $diseases
            }
        """)
        self.parameters["diseases"] = standardized
        return self

    def add_avoid_constraint(self, avoid_list: List[str]) -> 'MultiConstraintQueryBuilder':
        """添加禁忌约束 - 排除不适合的食物"""
        if not avoid_list:
            return self

        self.constraints.append("""
            NOT EXISTS {
                MATCH (f:Food)-[:AVOID_FOR]->(c:Crowd)
                WHERE c.name IN $avoid_list
            }
        """)
        self.parameters["avoid_list"] = avoid_list
        return self

    def add_calorie_constraint(self, min_cal: int = None, max_cal: int = None) -> 'MultiConstraintQueryBuilder':
        """添加热量约束"""
        conditions = []
        if min_cal is not None:
            conditions.append("f.calories >= $min_calories")
            self.parameters["min_calories"] = min_cal
        if max_cal is not None:
            conditions.append("f.calories <= $max_calories")
            self.parameters["max_calories"] = max_cal

        if conditions:
            self.constraints.append(f"f.calories >= {min_cal or 0} AND f.calories <= {max_cal or 9999}")

        return self

    def add_nutrient_constraint(self, required_nutrients: List[str] = None,
                                 min_protein: int = None,
                                 max_fat: int = None,
                                 min_fiber: int = None) -> 'MultiConstraintQueryBuilder':
        """添加营养素约束"""
        if required_nutrients:
            for nutrient in required_nutrients:
                self.constraints.append(f"""
                    EXISTS {{
                        MATCH (f:Food)-[:CONTAINS_NUTRIENT]->(:Nutrient {{name: $nutrient_{nutrient}}})
                    }}
                """)
                self.parameters[f"nutrient_{nutrient}"] = nutrient

        if min_protein is not None:
            self.constraints.append(f"f.protein >= {min_protein}")
            self.parameters["min_protein"] = min_protein

        if max_fat is not None:
            self.constraints.append(f"f.fat <= {max_fat}")
            self.parameters["max_fat"] = max_fat

        if min_fiber is not None:
            self.constraints.append(f"f.fiber >= {min_fiber}")
            self.parameters["min_fiber"] = min_fiber

        return self

    def add_meal_type_constraint(self, meal_type: str) -> 'MultiConstraintQueryBuilder':
        """添加餐类型约束"""
        if meal_type:
            self.constraints.append(f"f.meal_type = $meal_type")
            self.parameters["meal_type"] = meal_type
        return self

    def add_sodium_constraint(self, max_sodium: int = 500) -> 'MultiConstraintQueryBuilder':
        """添加钠含量约束（低钠饮食）"""
        self.constraints.append(f"f.sodium <= $max_sodium")
        self.parameters["max_sodium"] = max_sodium
        return self

    def build(self) -> Tuple[str, Dict]:
        """
        构建最终的Cypher查询

        Returns:
            (cypher_query, parameters)
        """
        where_clause = ""

        if self.constraints:
            # 过滤非空约束
            valid_constraints = [c.strip() for c in self.constraints if c.strip()]
            if valid_constraints:
                where_clause = "WHERE " + " AND ".join(valid_constraints)

        cypher = f"""
            MATCH (f:Food)
            {where_clause}
            RETURN f.name as name, f.category as category, f.calories as calories,
                   f.protein as protein, f.carbs as carbs, f.fat as fat,
                   f.fiber as fiber, f.sodium as sodium, f.portion as portion,
                   f.meal_type as meal_type
            ORDER BY f.calories ASC
            LIMIT 50
        """

        return cypher.strip(), self.parameters

    def execute(self) -> List[Dict]:
        """构建并执行查询"""
        cypher, params = self.build()
        return execute_cypher_query(cypher, params)


def build_query_from_metadata(user_metadata: Dict, user_requirement: Dict = None,
                               environment: Dict = None) -> List[Dict]:
    """
    根据用户信息构建多约束查询

    Args:
        user_metadata: 用户健康信息
        user_requirement: 用户需求
        environment: 环境信息

    Returns:
        符合条件的食物列表
    """
    builder = MultiConstraintQueryBuilder()

    # 1. 疾病约束
    diseases = user_metadata.get("medical_conditions", [])
    if diseases:
        builder.add_disease_constraint(diseases)
    else:
        # 默认适合健康人群
        builder.add_disease_constraint(["健康人群"])

    # 2. 饮食限制约束
    restrictions = user_metadata.get("dietary_restrictions", [])

    # 低钠限制
    if "low_sodium" in restrictions:
        builder.add_sodium_constraint(max_sodium=200)

    # 3. 热量约束（根据目标）
    goal = user_requirement.get("goal") if user_requirement else "maintain"
    bmi = user_metadata.get("bmi", 22)

    if goal == "weight_loss" or bmi > 25:
        # 减肥: 低热量
        builder.add_calorie_constraint(min_cal=100, max_cal=400)
    elif goal == "weight_gain" or bmi < 18.5:
        # 增重: 高热量
        builder.add_calorie_constraint(min_cal=300, max_cal=600)
    else:
        # 维持
        builder.add_calorie_constraint(min_cal=150, max_cal=500)

    # 4. 营养素约束
    fitness_level = user_metadata.get("fitness_level", "beginner")

    if fitness_level in ["intermediate", "advanced"]:
        # 健身人群需要高蛋白
        builder.add_nutrient_constraint(min_protein=15)

    # 5. 环境约束（天气/季节）
    if environment:
        season = environment.get("time_context", {}).get("season", "spring")
        weather = environment.get("weather", {}).get("condition", "clear")

        # 夏天推荐清淡食物
        if season == "summer":
            builder.add_nutrient_constraint(max_fat=10)
        # 雨天推荐温热食物（通过特殊标签，此处简化为排除冷食）
        if weather == "rainy":
            pass  # 可以在食物数据中添加温度属性后扩展

    # 执行查询
    return builder.execute()


def nl_query_with_context(question: str, user_metadata: Dict = None) -> List[Dict]:
    """
    结合NL和结构化查询的混合方法
    1. 用NL生成基础Cypher
    2. 用多约束构建器补充用户医学约束
    """
    # 先用多约束查询获取符合医学条件的食物
    structured_results = build_query_from_metadata(user_metadata or {})

    if not structured_results:
        # 如果结构化查询无结果，尝试纯NL查询
        cypher = nl_to_cypher(question, user_metadata)
        if cypher:
            structured_results = execute_cypher_query(cypher)

    return structured_results


# 保留原有函数（向后兼容）
def generate_cypher_for_query(user_metadata: Dict, user_requirement: Dict = None) -> str:
    """Generate Cypher query from natural language requirements using LLM"""
    conditions = user_metadata.get("medical_conditions", [])
    restrictions = user_metadata.get("dietary_restrictions", [])
    fitness_level = user_metadata.get("fitness_level", "beginner")
    goal = user_requirement.get("goal", "maintain") if user_requirement else "maintain"

    # Build context for LLM
    context = f"""
    用户条件:
    - 疾病: {conditions}
    - 饮食限制: {restrictions}
    - 健身水平: {fitness_level}
    - 目标: {goal}

    任务: 生成Cypher查询语句，从知识图谱中检索符合条件的食物。
    要求:
    1. 只查询Food类型的节点
    2. 考虑疾病禁忌和饮食限制
    3. 根据目标调整热量范围
    4. 返回格式: MATCH查询语句
    """

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是Neo4j Cypher查询专家。根据用户条件生成准确的Cypher查询。"},
                {"role": "user", "content": context}
            ],
            temperature=0.1
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Cypher generation failed: {e}")
        return None


# ================= Phase 3: Knowledge Retrieval Module =================

class KnowledgeRetrievalResult:
    """知识检索结果封装"""

    def __init__(self, foods: List[Dict], meal_type: str, constraints: Dict):
        self.foods = foods
        self.meal_type = meal_type
        self.constraints = constraints
        self._categorize()

    def _categorize(self):
        """按类别细分食物"""
        self.by_category = {}
        for food in self.foods:
            cat = food.get("category", "other")
            if cat not in self.by_category:
                self.by_category[cat] = []
            self.by_category[cat].append(food)

    def get_foods_for_meal(self, min_calories: int = None, max_calories: int = None) -> List[Dict]:
        """获取适合当前餐次的食物列表"""
        result = []
        for food in self.foods:
            cal = food.get("calories", 0)
            if min_calories and cal < min_calories:
                continue
            if max_calories and cal > max_calories:
                continue
            result.append(food)
        return result

    def get_diversity_score(self) -> float:
        """计算食物多样性分数"""
        if not self.foods:
            return 0
        categories = len(self.by_category)
        return min(1.0, categories / 5.0)  # 5个类别以上得满分


def retrieve_foods_by_constraints(
    constraints: Dict,
    meal_types: List[str] = None
) -> Dict[str, KnowledgeRetrievalResult]:
    """
    根据多维约束从知识图谱检索食物

    Args:
        constraints: 约束字典
            - diseases: List[str] - 疾病列表
            - avoid_foods: List[str] - 需避免的食物
            - max_calories: int - 最大热量
            - min_protein: int - 最小蛋白质
            - max_fat: int - 最大脂肪
            - min_fiber: int - 最小纤维
            - max_sodium: int - 最大钠
        meal_types: 餐次类型列表

    Returns:
        Dict[meal_type, KnowledgeRetrievalResult]
    """
    if meal_types is None:
        meal_types = ["breakfast", "lunch", "dinner", "snacks"]

    results = {}

    for meal_type in meal_types:
        # 计算该餐次的目标热量
        max_cal = constraints.get("max_calories", 500) // 4
        if meal_type == "snacks":
            max_cal = constraints.get("max_calories", 200) // 4

        # 构建Cypher查询
        query_parts = ["MATCH (f:Food)"]
        params = {}

        # 疾病约束
        diseases = constraints.get("diseases", [])
        if diseases:
            disease_map = {
                "diabetes": "糖尿病", "糖尿病": "糖尿病",
                "hypertension": "高血压", "高血压": "高血压",
                "hyperlipidemia": "高血脂", "高血脂": "高血脂",
            }
            std_diseases = [disease_map.get(d, d) for d in diseases]
            query_parts.append("""
                MATCH (f)-[:SUITABLE_FOR]->(c:Crowd)
                WHERE c.name IN $diseases
            """)
            params["diseases"] = std_diseases

        # 餐类型
        query_parts.append("WHERE f.meal_type = $meal_type")
        params["meal_type"] = meal_type

        # 热量约束
        if max_cal:
            query_parts.append("AND f.calories <= $max_calories")
            params["max_calories"] = max_cal

        # 蛋白质约束
        min_protein = constraints.get("min_protein")
        if min_protein:
            query_parts.append("AND f.protein >= $min_protein")
            params["min_protein"] = min_protein

        # 脂肪约束
        max_fat = constraints.get("max_fat")
        if max_fat:
            query_parts.append("AND f.fat <= $max_fat")
            params["max_fat"] = max_fat

        # 钠约束
        max_sodium = constraints.get("max_sodium")
        if max_sodium:
            query_parts.append("AND f.sodium <= $max_sodium")
            params["max_sodium"] = max_sodium

        query_parts.append("""
            RETURN f.name as name, f.category as category, f.calories as calories,
                   f.protein as protein, f.carbs as carbs, f.fat as fat,
                   f.fiber as fiber, f.sodium as sodium, f.portion as portion
            LIMIT 100
        """)

        cypher = " ".join(query_parts)

        # 执行查询
        with driver.session() as session:
            try:
                result = session.run(cypher, params)
                foods = [dict(rec) for rec in result]
            except Exception as e:
                print(f"[Knowledge Retrieval] Error for {meal_type}: {e}")
                foods = []

        results[meal_type] = KnowledgeRetrievalResult(foods, meal_type, constraints)

    return results


def retrieve_with_kg_context(
    user_metadata: Dict,
    environment: Dict = None
) -> Dict[str, KnowledgeRetrievalResult]:
    """
    从知识图谱检索食物（使用图谱上下文）

    1. 查询用户的疾病/禁忌在图谱中的关联食物
    2. 获取营养建议
    3. 组合检索结果
    """
    diseases = user_metadata.get("medical_conditions", [])
    restrictions = user_metadata.get("dietary_restrictions", [])

    constraints = {
        "diseases": diseases,
        "avoid_foods": [],
        "max_calories": user_metadata.get("target_calories", 1800),
        "min_protein": None,
        "max_fat": None,
        "min_fiber": None,
        "max_sodium": 500
    }

    # 低钠饮食
    if "low_sodium" in restrictions:
        constraints["max_sodium"] = 200

    # 健身人群高蛋白
    fitness = user_metadata.get("fitness_level")
    if fitness in ["intermediate", "advanced"]:
        constraints["min_protein"] = 15

    # 环境因素
    if environment:
        season = environment.get("time_context", {}).get("season")
        if season == "summer":
            constraints["max_fat"] = 10  # 夏天清淡

    # 执行检索
    return retrieve_foods_by_constraints(constraints)


# ================= Phase 3: Meal Plan Sampler =================

class MealPlanSampler:
    """
    餐计划采样器
    - 加权随机采样
    - 营养均衡保证
    - 多样性保证
    """

    def __init__(self, foods_pool: Dict[str, KnowledgeRetrievalResult]):
        self.foods_pool = foods_pool
        self.sampling_log = []

    def _calculate_weight(self, food: Dict, target_calories: int, weight_strategy: str = "balanced") -> float:
        """
        计算食物采样权重

        Strategies:
        - balanced: 平衡策略
        - calorie_optimal: 热量最优
        - protein_priority: 蛋白质优先
        - variety_priority: 多样性优先
        """
        cal = food.get("calories", 100)
        protein = food.get("protein", 0)
        fat = food.get("fat", 0)

        if weight_strategy == "calorie_optimal":
            # 热量越接近目标越好
            cal_diff = abs(cal - target_calories)
            return 1.0 / (cal_diff + 1)

        elif weight_strategy == "protein_priority":
            # 蛋白质越高权重越大
            return max(0.1, protein / 10.0)

        elif weight_strategy == "balanced":
            # 综合评分
            cal_score = 1.0 / (abs(cal - target_calories) + 1)
            protein_score = protein / 20.0
            fat_penalty = fat / 30.0
            return cal_score * 0.4 + protein_score * 0.4 - fat_penalty * 0.2

        else:  # variety_priority
            return 1.0  # 均匀分布

    def _weighted_sample(self, items: List[Dict], target_calories: int,
                         strategy: str = "balanced", count: int = 1) -> List[Dict]:
        """加权随机采样"""
        if not items:
            return []
        if len(items) <= count:
            return items[:count]

        weights = [self._calculate_weight(item, target_calories, strategy) for item in items]
        total = sum(weights)
        probs = [w / total for w in weights]

        import random
        selected = random.choices(items, weights=probs, k=count)
        return selected

    def sample_meal(
        self,
        meal_type: str,
        target_calories: int,
        strategy: str = "balanced",
        must_include_categories: List[str] = None
    ) -> Dict:
        """
        采样单餐

        Returns:
            Dict with food items, total calories, macros
        """
        retrieval = self.foods_pool.get(meal_type)
        if not retrieval or not retrieval.foods:
            # 使用默认食物
            available = FOOD_DATABASE.get(meal_type, [])
        else:
            available = retrieval.get_foods_for_meal(max_calories=target_calories * 1.5)

        if not available:
            return {
                "meal_type": meal_type,
                "items": [],
                "calories": 0,
                "protein": 0,
                "carbs": 0,
                "fat": 0
            }

        # 如果需要特定类别，优先选择
        if must_include_categories:
            prioritized = [f for f in available if f.get("category") in must_include_categories]
            if prioritized:
                available = prioritized

        # 加权采样
        selected = self._weighted_sample(available, target_calories, strategy)

        # 计算营养
        total_cal = sum(f.get("calories", 0) for f in selected)
        total_protein = sum(f.get("protein", 0) for f in selected)
        total_carbs = sum(f.get("carbs", 0) for f in selected)
        total_fat = sum(f.get("fat", 0) for f in selected)

        return {
            "meal_type": meal_type,
            "items": [
                {
                    "food": f["name"],
                    "portion": f"{f.get('portion', 100)}g",
                    "calories": f.get("calories", 0)
                }
                for f in selected
            ],
            "calories": total_cal,
            "protein": total_protein,
            "carbs": total_carbs,
            "fat": total_fat
        }

    def generate_meal_plan(
        self,
        target_calories: int,
        num_candidates: int = 3,
        strategy: str = "balanced"
    ) -> List[Dict]:
        """
        生成完整餐计划（多候选）

        Args:
            target_calories: 目标热量
            num_candidates: 候选数量
            strategy: 采样策略

        Returns:
            List[餐计划Dict]
        """
        candidates = []

        # 餐次分配
        meal_distribution = {
            "breakfast": target_calories * 0.25,
            "lunch": target_calories * 0.35,
            "dinner": target_calories * 0.30,
            "snack": target_calories * 0.10
        }

        for i in range(num_candidates):
            meal_plan = {}
            macros = {"protein": 0, "carbs": 0, "fat": 0}

            for meal_type, target in meal_distribution.items():
                meal = self.sample_meal(meal_type, target, strategy)
                meal_plan[meal_type] = meal["items"]
                macros["protein"] += meal["protein"]
                macros["carbs"] += meal["carbs"]
                macros["fat"] += meal["fat"]

            # 计算总热量
            total_cal = sum(
                sum(item.get("calories", 0) for item in items)
                for items in meal_plan.values()
            )

            # 评估
            calories_deviation = abs(total_cal - target_calories) / target_calories
            protein_ratio = macros["protein"] * 4 / total_cal if total_cal > 0 else 0

            candidates.append({
                "id": i + 1,
                "meal_plan": meal_plan,
                "total_calories": total_cal,
                "calories_deviation": round(calories_deviation * 100, 1),  # 百分比
                "macro_nutrients": {
                    "protein": round(macros["protein"], 1),
                    "carbs": round(macros["carbs"], 1),
                    "fat": round(macros["fat"], 1),
                    "protein_ratio": round(protein_ratio * 100, 1)  # 蛋白质供能比
                },
                "sampling_strategy": strategy,
                "safety_notes": []
            })

            # 添加安全提示
            if calories_deviation > 0.2:
                candidates[-1]["safety_notes"].append(f"热量偏差较大: {total_cal} vs {target_calories}")
            if protein_ratio < 0.15:
                candidates[-1]["safety_notes"].append("蛋白质供能比偏低，建议增加优质蛋白")

        # 按热量偏差排序
        candidates.sort(key=lambda x: x["calories_deviation"])

        return candidates

    def apply_nutrition_balance_rules(self, candidate: Dict) -> Dict:
        """
        应用营养均衡规则优化餐计划

        Rules:
        1. 蛋白质占总热量15-25%
        2. 脂肪占总热量20-35%
        3. 碳水占总热量45-65%
        """
        macros = candidate["macro_nutrients"]
        total = macros["protein"] * 4 + macros["carbs"] * 4 + macros["fat"] * 9

        if total == 0:
            return candidate

        protein_pct = macros["protein"] * 4 / total * 100
        fat_pct = macros["fat"] * 9 / total * 100
        carbs_pct = macros["carbs"] * 4 / total * 100

        suggestions = []

        if protein_pct < 15:
            suggestions.append("蛋白质偏低，建议增加鱼、肉、豆制品")
        elif protein_pct > 25:
            suggestions.append("蛋白质偏高，可适当减少")

        if fat_pct > 35:
            suggestions.append("脂肪偏高，建议减少油炸食品")
        elif fat_pct < 20:
            suggestions.append("脂肪偏低，可适量增加坚果")

        candidate["nutrition_analysis"] = {
            "protein_pct": round(protein_pct, 1),
            "fat_pct": round(fat_pct, 1),
            "carbs_pct": round(carbs_pct, 1),
            "suggestions": suggestions
        }

        return candidate


def sample_meal_plans(foods_pool: Dict, num_candidates: int = 3, target_calories: int = None) -> List[Dict]:
    """Sample and compose meal plans from food pool (simplified version)"""
    import random

    if target_calories is None:
        target_calories = 1800

    candidates = []

    # 餐次热量分配
    meal_targets = {
        "breakfast": target_calories * 0.25,
        "lunch": target_calories * 0.35,
        "dinner": target_calories * 0.30,
        "snack": target_calories * 0.10
    }

    for _ in range(num_candidates):
        meal_plan = {}
        total_cal = 0
        macros = {"protein": 0, "carbs": 0, "fat": 0}

        for meal_type, target in meal_targets.items():
            available = foods_pool.get(meal_type, [])
            if not available:
                available = FOOD_DATABASE.get(meal_type, [])

            if available:
                food = random.choice(available)
                portion = food.get("capacity", 100)
                cal = food.get("calories", 0)

                meal_plan[meal_type] = [{
                    "food": food["name"],
                    "portion": f"{portion}g",
                    "calories": cal
                }]

                total_cal += cal
                macros["protein"] += food.get("protein", 0)
                macros["carbs"] += food.get("carbs", 0)
                macros["fat"] += food.get("fat", 0)

        candidates.append({
            "meal_plan": meal_plan,
            "total_calories": total_cal,
            "macro_nutrients": macros,
            "safety_notes": []
        })

    return candidates


def generate_diet_candidates(
    user_metadata: Dict,
    environment: Dict = None,
    user_requirement: Dict = None,
    num_candidates: int = 3,
    sampling_strategy: str = "balanced"
) -> Dict[str, Any]:
    """
    Main function to generate diet plan candidates.

    Args:
        user_metadata: User health information
        environment: Weather/time context (optional)
        user_requirement: User preferences (optional)
        num_candidates: Number of candidates to generate
        sampling_strategy: Sampling strategy (balanced/calorie_optimal/protein_priority/variety_priority)

    Returns:
        Dict with 'candidates' list containing meal plans
    """
    # Calculate target calories based on goal
    bmi = user_metadata.get("bmi", 22)
    goal = user_requirement.get("goal", "maintain") if user_requirement else "maintain"

    if goal == "weight_loss" or bmi > 25:
        target_calories = 1500
    elif goal == "weight_gain" or bmi < 18.5:
        target_calories = 2200
    else:
        target_calories = 1800

    # Build conditions
    conditions = set(user_metadata.get("medical_conditions", []))
    conditions.add("健康人群")

    # Retrieve foods from knowledge graph
    retrieval_results = retrieve_with_kg_context(user_metadata, environment)

    # Create sampler and generate plans
    sampler = MealPlanSampler(retrieval_results)
    candidates = sampler.generate_meal_plan(
        target_calories=target_calories,
        num_candidates=num_candidates,
        strategy=sampling_strategy
    )

    # Apply nutrition balance rules
    for candidate in candidates:
        sampler.apply_nutrition_balance_rules(candidate)
        candidate["safety_notes"].append(f"目标热量: {target_calories}kcal, 实际: {candidate['total_calories']}kcal")

    return {
        "candidates": candidates,
        "target_calories": target_calories,
        "user_conditions": list(conditions),
        "sampling_strategy": sampling_strategy,
        "retrieval_stats": {
            "retrieved_meal_types": list(retrieval_results.keys()),
            "has_kg_data": any(r.foods for r in retrieval_results.values())
        }
    }


if __name__ == "__main__":
    # Test the module
    test_metadata = {
        "age": 35,
        "gender": "male",
        "height_cm": 175,
        "weight_kg": 70,
        "bmi": 22.9,
        "medical_conditions": ["糖尿病"],
        "dietary_restrictions": ["low_sodium"],
        "fitness_level": "intermediate"
    }

    test_environment = {
        "weather": {"condition": "clear", "temperature_c": 25},
        "time_context": {"season": "summer", "time_of_day": "morning"}
    }

    print("=== 测试 Phase 3: 知识检索 + 餐计划采样 ===\n")

    # 测试知识检索
    print("1. 测试 retrieve_foods_by_constraints:")
    constraints = {
        "diseases": ["糖尿病"],
        "max_calories": 1800,
        "max_sodium": 200
    }
    retrieval = retrieve_foods_by_constraints(constraints)
    for meal_type, result in retrieval.items():
        print(f"  {meal_type}: {len(result.foods)} 个食物, 多样性: {result.get_diversity_score():.2f}")

    # 测试餐计划生成
    print("\n2. 测试 generate_diet_candidates:")
    result = generate_diet_candidates(
        test_metadata,
        environment=test_environment,
        user_requirement={"goal": "weight_loss"},
        num_candidates=3,
        sampling_strategy="balanced"
    )

    print(f"目标热量: {result['target_calories']} kcal")
    print(f"采样策略: {result['sampling_strategy']}")
    print(f"检索统计: {result['retrieval_stats']}")

    for candidate in result["candidates"][:2]:  # 只显示前2个
        print(f"\n候选 {candidate['id']}:")
        print(f"  总热量: {candidate['total_calories']} kcal (偏差: {candidate['calories_deviation']}%)")
        print(f"  营养素: 蛋白{candidate['macro_nutrients']['protein']}g, "
              f"碳水{candidate['macro_nutrients']['carbs']}g, "
              f"脂肪{candidate['macro_nutrients']['fat']}g")
        print(f"  蛋白质供能比: {candidate['macro_nutrients'].get('protein_ratio', 'N/A')}%")
        if "nutrition_analysis" in candidate:
            print(f"  营养分析: 蛋白{candidate['nutrition_analysis']['protein_pct']}%, "
                  f"脂肪{candidate['nutrition_analysis']['fat_pct']}%")
        for note in candidate["safety_notes"]:
            print(f"  安全提示: {note}")
