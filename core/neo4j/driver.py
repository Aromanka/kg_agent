"""
Neo4j Database Driver
封装 Neo4j 数据库连接和常用操作
"""
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from config_loader import NEO4J_URI, NEO4J_AUTH, get_config


def get_driver():
    """获取 Neo4j 驱动实例"""
    neo4j_config = get_config()["neo4j"]
    return GraphDatabase.driver(
        neo4j_config["uri"],
        auth=(neo4j_config["username"], neo4j_config["password"])
    )


class Neo4jClient:
    """Neo4j 客户端封装类"""

    def __init__(self, driver=None):
        self.driver = driver or get_driver()

    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()

    def query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: str = "neo4j"
    ):  # -> List[Record]:
        """执行查询，返回记录列表"""
        with self.driver.session(database=database) as session:
            result = session.run(query, parameters)
            return list(result)

    def query_single(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: str = "neo4j"
    ):  # -> Optional[Record]:
        """执行查询，返回单条记录"""
        results = self.query(query, parameters, database)
        return results[0] if results else None

    def create_node(
        self,
        label: str,
        properties: Dict[str, Any],
        database: str = "neo4j"
    ) -> str:
        """创建节点，返回创建语句"""
        props_str = ", ".join([f"{k}: ${k}" for k in properties.keys()])
        query = f"CREATE (n:{label} {{{props_str}}})"
        with self.driver.session(database=database) as session:
            session.run(query, properties)
        return query

    def create_relationship(
        self,
        from_label: str,
        from_property: Dict[str, Any],
        rel_type: str,
        to_label: str,
        to_property: Dict[str, Any],
        rel_properties: Optional[Dict[str, Any]] = None,
        database: str = "neo4j"
    ) -> str:
        """创建关系"""
        from_str = " AND ".join([f"n.{k} = ${k}" for k in from_property.keys()])
        to_str = " AND ".join([f"m.{k} = ${k}" for k in to_property.keys()])
        props_str = ""
        if rel_properties:
            props_str = ", " + ", ".join([f"r.{k} = ${k}" for k in rel_properties.keys()])
            params = {**from_property, **to_property, **rel_properties}
        else:
            params = {**from_property, **to_property}
        query = f"""
        MATCH (n:{from_label}), (m:{to_label})
        WHERE {from_str} AND {to_str}
        CREATE (n)-[r:{rel_type}{{{props_str}}}]->(m)
        RETURN r
        """
        with self.driver.session(database=database) as session:
            session.run(query, params)
        return query

    def search_by_keyword(
        self,
        keyword: str,
        score_threshold: float = 0.6,
        database: str = "neo4j"
    ) -> List[Dict[str, Any]]:
        """使用全文索引搜索节点"""
        query = """
        CALL db.index.fulltext.queryNodes("search_index", $word) YIELD node, score
        WHERE score > $threshold
        MATCH (node)-[r]-(m)
        RETURN node.name as head, r.type as rel_type, m.name as tail, r.amount as amount, r.unit as unit
        """
        results = self.query(query, {"word": keyword, "threshold": score_threshold}, database)
        return [dict(record) for record in results]

    def get_node_by_name(
        self,
        name: str,
        label: Optional[str] = None,
        database: str = "neo4j"
    ) -> Optional[Dict[str, Any]]:
        """根据名称查找节点"""
        if label:
            query = f"""
            MATCH (n:{label} {{name: $name}})
            RETURN n
            """
        else:
            query = """
            MATCH (n {name: $name})
            RETURN n
            """
        result = self.query_single(query, {"name": name}, database)
        return dict(result["n"]) if result else None

    def get_neighbors(
        self,
        node_name: str,
        rel_types: Optional[List[str]] = None,
        database: str = "neo4j"
    ) -> List[Dict[str, Any]]:
        """获取节点的邻居节点"""
        if rel_types:
            rel_filter = "|".join(rel_types)
            query = f"""
            MATCH (n {{name: $name}})-[r:`{rel_filter}`]-(m)
            RETURN m.name as neighbor, r.type as rel_type, r
            """
        else:
            query = """
            MATCH (n {name: $name})-[r]-(m)
            RETURN m.name as neighbor, r.type as rel_type, r
            """
        results = self.query(query, {"name": node_name}, database)
        return [dict(record) for record in results]

    def delete_all(self, database: str = "neo4j"):
        """删除所有节点和关系（慎用）"""
        with self.driver.session(database=database) as session:
            session.run("MATCH (n) DETACH DELETE n")


# 全局客户端实例
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j() -> Neo4jClient:
    """获取全局 Neo4j 客户端实例"""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    return _neo4j_client


# 兼容旧代码的 driver 实例
driver = get_driver()
