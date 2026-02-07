"""
Neo4j Query Utilities
提供常用的知识图谱查询功能
"""
from typing import List, Dict, Any, Optional
from .driver import Neo4jClient, get_neo4j


class KnowledgeGraphQuery:
    """知识图谱查询工具类"""

    def __init__(self, client: Optional[Neo4jClient] = None):
        self.client = client or get_neo4j()

    # ================= 饮食相关查询 =================

    def query_foods_by_disease(self, disease: str) -> List[Dict[str, Any]]:
        """查询某疾病的推荐饮食"""
        # Try specific labels first, fallback to Entity
        query = """
        MATCH (d)-[:Diet_Disease]-(f)
        WHERE toLower(d.name) = toLower($disease)
        RETURN f.name as food, f.category as category
        LIMIT 20
        """
        return self.client.query(query, {"disease": disease})

    def query_foods_for_condition(self, condition: str) -> List[Dict[str, Any]]:
        """查询某种健康状况的适宜饮食"""
        query = """
        MATCH (n)-[r:Food_Diet]->(m)
        WHERE toLower(n.name) CONTAINS toLower($condition) OR toLower($condition) CONTAINS toLower(n.name)
        RETURN n.name as entity, type(r) as relation, m.name as diet_recommendation
        """
        return self.client.query(query, {"condition": condition})

    def query_dietary_restrictions(self, disease: str) -> List[Dict[str, Any]]:
        """查询某疾病的饮食禁忌"""
        query = """
        MATCH (d)-[r:Restriction_Disease]->(rstr)
        WHERE toLower(d.name) = toLower($disease)
        RETURN rstr.name as restriction, r.description as description
        LIMIT 20
        """
        return self.client.query(query, {"disease": disease})

    def query_nutrient_advice(self, disease: str) -> List[Dict[str, Any]]:
        """查询某疾病的营养建议"""
        query = """
        MATCH (n)-[r:Nutrient_Disease]->(d)
        WHERE toLower(d.name) = toLower($disease)
        RETURN n.name as nutrient, r.advice as advice, r.amount as amount
        LIMIT 20
        """
        return self.client.query(query, {"disease": disease})

    def query_food_benefits(self, food: str) -> List[Dict[str, Any]]:
        """查询食物的益处"""
        query = """
        MATCH (f)-[r:Benefit_Food]->(b)
        WHERE toLower(f.name) CONTAINS toLower($food)
        RETURN b.name as benefit, r.description as description
        LIMIT 10
        """
        return self.client.query(query, {"food": food})

    def query_food_risks(self, food: str) -> List[Dict[str, Any]]:
        """查询食物的风险"""
        query = """
        MATCH (f)-[r:Risk_Food]->(rsk)
        WHERE toLower(f.name) CONTAINS toLower($food)
        RETURN rsk.name as risk, r.description as description
        LIMIT 10
        """
        return self.client.query(query, {"food": food})

    def query_food_conflicts(self, food: str) -> List[Dict[str, Any]]:
        """查询食物的冲突/禁忌"""
        query = """
        MATCH (f)-[r:Food_Disease]->(d)
        WHERE toLower(f.name) CONTAINS toLower($food)
        RETURN d.name as disease, r.description as description
        LIMIT 10
        """
        return self.client.query(query, {"food": food})

    # ================= 运动相关查询 =================

    def query_exercise_for_condition(self, condition: str) -> List[Dict[str, Any]]:
        """查询某种健康状况的推荐运动"""
        query = """
        MATCH (e:Exercise)-[:Target_Recommendation]->(c:Condition)
        WHERE toLower(c.name) CONTAINS toLower($condition) OR toLower($condition) CONTAINS toLower(c.name)
        RETURN e.name as exercise, e.type as type, e.intensity as intensity
        LIMIT 20
        """
        results = self.client.query(query, {"condition": condition})
        if not results:
            # Try Disease_Management relation
            query = """
            MATCH (e:Exercise)-[:Disease_Management]->(d:Condition)
            WHERE toLower(d.name) CONTAINS toLower($condition)
            RETURN e.name as exercise, e.type as type, e.intensity as intensity
            LIMIT 20
            """
            results = self.client.query(query, {"condition": condition})
        return results

    def query_exercise_avoid_for_condition(self, condition: str) -> List[Dict[str, Any]]:
        """查询某种健康状况应该避免的运动"""
        query = """
        MATCH (e:Exercise)-[:Target_Avoid]->(c:Condition)
        WHERE toLower(c.name) CONTAINS toLower($condition)
        RETURN e.name as exercise, e.type as type, r.reason as reason
        LIMIT 20
        """
        return self.client.query(query, {"condition": condition})

    def query_exercise_risks(
        self,
        exercise: str = None,
        condition: str = None
    ) -> List[Dict[str, Any]]:
        """查询运动的风险或禁忌"""
        if condition:
            query = """
            MATCH (e:Exercise)-[:Has_Risk]->(r:Risk)
            MATCH (e)-[:Target_Avoid]->(c:Condition)
            WHERE toLower(c.name) CONTAINS toLower($condition)
            RETURN e.name as exercise, r.name as risk, r.description as description
            LIMIT 20
            """
            return self.client.query(query, {"condition": condition})
        elif exercise:
            query = """
            MATCH (e:Exercise)-[:Has_Risk]->(r:Risk)
            WHERE toLower(e.name) CONTAINS toLower($exercise)
            RETURN r.name as risk, r.description as description
            LIMIT 10
            """
            return self.client.query(query, {"exercise": exercise})
        return []

    def query_exercise_benefits(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的益处"""
        query = """
        MATCH (e:Exercise)-[:Has_Benefit]->(b:Benefit)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN b.name as benefit, b.description as description
        LIMIT 10
        """
        return self.client.query(query, {"exercise": exercise})

    def query_exercise_targets_muscle(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动针对的肌肉群"""
        query = """
        MATCH (e:Exercise)-[:Targets_Muscle]->(m:Muscle)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN m.name as muscle_group, m.description as description
        LIMIT 10
        """
        return self.client.query(query, {"exercise": exercise})

    def query_exercise_duration(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的推荐时长"""
        query = """
        MATCH (e:Exercise)-[:Recommended_Duration]->(d:Duration)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN d.amount as duration, d.unit as unit, d.description as description
        LIMIT 10
        """
        return self.client.query(query, {"exercise": exercise})

    def query_exercise_frequency(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的推荐频率"""
        query = """
        MATCH (e:Exercise)-[:Recommended_Freq]->(f:Frequency)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN f.frequency as frequency, f.description as description
        LIMIT 10
        """
        return self.client.query(query, {"exercise": exercise})

    def query_exercise_substitutes(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的替代方案"""
        query = """
        MATCH (e:Exercise)-[:Substitute_With]->(s:Exercise)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN s.name as substitute, s.type as type, s.intensity as intensity
        LIMIT 10
        """
        return self.client.query(query, {"exercise": exercise})

    def query_exercise_by_type(
        self,
        exercise_type: str,
        intensity: str = None
    ) -> List[Dict[str, Any]]:
        """按类型和强度查询运动"""
        query = """
        MATCH (e:Exercise)
        WHERE toLower(e.type) = toLower($type)
        """
        params = {"type": exercise_type}

        if intensity:
            query += " AND toLower(e.intensity) = toLower($intensity)"
            params["intensity"] = intensity

        query += """
        RETURN e.name as name, e.type as type, e.intensity as intensity,
               e.calories_per_minute as cpm, e.equipment as equipment
        LIMIT 30
        """
        return self.client.query(query, params)

    def query_all_exercises(self, limit: int = 50) -> List[Dict[str, Any]]:
        """查询所有运动实体"""
        query = """
        MATCH (e:Exercise)
        RETURN e.name as name, e.type as type, e.intensity as intensity,
               e.calories_per_minute as cpm, e.equipment as equipment
        LIMIT $limit
        """
        return self.client.query(query, {"limit": limit})

    # ================= 通用查询 =================

    def search_entities(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """通用实体搜索"""
        return self.client.search_by_keyword(keyword, score_threshold=0.5)

    def get_entity_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取实体完整信息"""
        node = self.client.get_node_by_name(name)
        if node:
            neighbors = self.client.get_neighbors(name)
            return {"node": node, "neighbors": neighbors}
        return None


# 全局查询实例
_kg_query: Optional[KnowledgeGraphQuery] = None


def get_kg_query() -> KnowledgeGraphQuery:
    """获取全局知识图谱查询实例"""
    global _kg_query
    if _kg_query is None:
        _kg_query = KnowledgeGraphQuery()
    return _kg_query
