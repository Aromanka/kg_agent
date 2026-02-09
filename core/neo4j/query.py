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

    def _safe_query(self, pattern: str, params: dict):
        """Execute a query, return empty list if fails"""
        try:
            return self.client.query(pattern, params)
        except Exception as e:
            print(f"[WARN] Query failed: {e}")
            return []

    def query_foods_by_disease(self, disease: str) -> List[Dict[str, Any]]:
        """查询某疾病的推荐饮食 - generic query for any relationship"""
        pattern = """
        MATCH (d)-[r]->(f)
        WHERE toLower(d.name) = toLower($disease)
        RETURN f.name as food, type(r) as relation
        LIMIT 20
        """
        return self._safe_query(pattern, {"disease": disease})

    def query_foods_for_condition(self, condition: str) -> List[Dict[str, Any]]:
        """查询某种健康状况的适宜饮食"""
        pattern = """
        MATCH (n)-[r]->(m)
        WHERE toLower(n.name) CONTAINS toLower($condition)
           OR toLower($condition) CONTAINS toLower(n.name)
        RETURN n.name as entity, type(r) as relation, m.name as target
        """
        return self._safe_query(pattern, {"condition": condition})

    def query_dietary_restrictions(self, disease: str) -> List[Dict[str, Any]]:
        """查询某疾病的饮食禁忌"""
        pattern = """
        MATCH (d)-[r]->(rstr)
        WHERE toLower(d.name) = toLower($disease)
        RETURN rstr.name as entity, type(r) as relation
        LIMIT 20
        """
        return self._safe_query(pattern, {"disease": disease})

    def query_nutrient_advice(self, disease: str) -> List[Dict[str, Any]]:
        """查询某疾病的营养建议"""
        pattern = """
        MATCH (n)-[r]->(d)
        WHERE toLower(d.name) = toLower($disease)
        RETURN n.name as entity, type(r) as relation
        LIMIT 20
        """
        return self._safe_query(pattern, {"disease": disease})

    def query_food_benefits(self, food: str) -> List[Dict[str, Any]]:
        """查询食物的益处"""
        pattern = """
        MATCH (f)-[r]->(b)
        WHERE toLower(f.name) CONTAINS toLower($food)
        RETURN b.name as entity, type(r) as relation
        LIMIT 10
        """
        return self._safe_query(pattern, {"food": food})

    def query_food_risks(self, food: str) -> List[Dict[str, Any]]:
        """查询食物的风险"""
        pattern = """
        MATCH (f)-[r]->(rsk)
        WHERE toLower(f.name) CONTAINS toLower($food)
        RETURN rsk.name as entity, type(r) as relation
        LIMIT 10
        """
        return self._safe_query(pattern, {"food": food})

    def query_food_conflicts(self, food: str) -> List[Dict[str, Any]]:
        """查询食物的冲突/禁忌"""
        pattern = """
        MATCH (f)-[r]->(d)
        WHERE toLower(f.name) CONTAINS toLower($food)
        RETURN d.name as entity, type(r) as relation
        LIMIT 10
        """
        return self._safe_query(pattern, {"food": food})

    # ================= 运动相关查询 =================

    def query_exercise_for_condition(self, condition: str) -> List[Dict[str, Any]]:
        """查询某种健康状况的推荐运动 - generic"""
        pattern = """
        MATCH (e)-[r]->(c)
        WHERE toLower(c.name) CONTAINS toLower($condition)
           OR toLower($condition) CONTAINS toLower(c.name)
        RETURN e.name as entity, type(r) as relation, labels(e) as labels
        LIMIT 20
        """
        return self._safe_query(pattern, {"condition": condition})

    def query_exercise_avoid_for_condition(self, condition: str) -> List[Dict[str, Any]]:
        """查询某种健康状况应该避免的运动"""
        pattern = """
        MATCH (e)-[r]->(c)
        WHERE toLower(c.name) CONTAINS toLower($condition)
        RETURN e.name as entity, type(r) as relation, labels(e) as labels
        LIMIT 20
        """
        return self._safe_query(pattern, {"condition": condition})

    def query_exercise_risks(
        self,
        exercise: str = None,
        condition: str = None
    ) -> List[Dict[str, Any]]:
        """查询运动的风险或禁忌"""
        if condition:
            pattern = """
            MATCH (e)-[r]->(c)
            WHERE toLower(c.name) CONTAINS toLower($condition)
            RETURN e.name as entity, type(r) as relation, labels(e) as labels
            LIMIT 20
            """
            return self._safe_query(pattern, {"condition": condition})
        elif exercise:
            pattern = """
            MATCH (e)-[r]->(target)
            WHERE toLower(e.name) CONTAINS toLower($exercise)
            RETURN target.name as entity, type(r) as relation, labels(target) as labels
            LIMIT 10
            """
            return self._safe_query(pattern, {"exercise": exercise})
        return []

    def query_exercise_benefits(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的益处"""
        pattern = """
        MATCH (e)-[r]->(b)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN b.name as entity, type(r) as relation, labels(b) as labels
        LIMIT 10
        """
        return self._safe_query(pattern, {"exercise": exercise})

    def query_exercise_targets_muscle(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动针对的肌肉群"""
        pattern = """
        MATCH (e)-[r]->(m)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN m.name as entity, type(r) as relation, labels(m) as labels
        LIMIT 10
        """
        return self._safe_query(pattern, {"exercise": exercise})

    def query_exercise_duration(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的推荐时长"""
        pattern = """
        MATCH (e)-[r]->(d)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN d.name as entity, type(r) as relation, labels(d) as labels
        LIMIT 10
        """
        return self._safe_query(pattern, {"exercise": exercise})

    def query_exercise_frequency(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的推荐频率"""
        pattern = """
        MATCH (e)-[r]->(f)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN f.name as entity, type(r) as relation, labels(f) as labels
        LIMIT 10
        """
        return self._safe_query(pattern, {"exercise": exercise})

    def query_exercise_substitutes(self, exercise: str) -> List[Dict[str, Any]]:
        """查询运动的替代方案"""
        pattern = """
        MATCH (e)-[r]->(s)
        WHERE toLower(e.name) CONTAINS toLower($exercise)
        RETURN s.name as entity, type(r) as relation, labels(s) as labels
        LIMIT 10
        """
        return self._safe_query(pattern, {"exercise": exercise})

    def query_exercise_by_type(
        self,
        exercise_type: str,
        intensity: str = None
    ) -> List[Dict[str, Any]]:
        """按类型查询运动 - generic"""
        pattern = """
        MATCH (e)
        WHERE toLower(e.type) = toLower($type)
        """
        params = {"type": exercise_type}

        if intensity:
            pattern += " AND toLower(e.intensity) = toLower($intensity)"
            params["intensity"] = intensity

        pattern += """
        RETURN e.name as name, labels(e) as labels
        LIMIT 30
        """
        return self._safe_query(pattern, params)

    def query_all_exercises(self, limit: int = 50) -> List[Dict[str, Any]]:
        """查询所有实体（不限定标签）"""
        pattern = """
        MATCH (e)
        RETURN e.name as name, labels(e) as labels
        LIMIT $limit
        """
        return self._safe_query(pattern, {"limit": limit})

    # ================= 通用查询 =================

    def search_entities(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """通用实体搜索"""
        return self.client.search_by_keyword(keyword, score_threshold=0.2)

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
