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
        RETURN n.name as entity, r.type as relation, m.name as diet_recommendation
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

    # ================= 运动相关查询 (待知识图谱补充) =================

    def query_exercise_for_condition(self, condition: str) -> List[Dict[str, Any]]:
        """查询某种健康状况的适宜运动"""
        # 预留接口，知识图谱需补充运动数据
        return []

    def query_exercise_risks(self, exercise: str, condition: str) -> List[Dict[str, Any]]:
        """查询某种运动对某健康状况的风险"""
        # 预留接口
        return []

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
