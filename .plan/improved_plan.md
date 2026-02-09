基于该代码仓库（`kg_agent`）目前的架构，引入 **GraphRAG（Graph Retrieval-Augmented Generation）** 最简单、侵入性最小的方案是实现 **“基于向量检索的局部子图 RAG” (Vector-based Local Graph RAG)**。

目前的检索逻辑是基于“关键词精确匹配” (`keyword matching`)，这导致无法处理语义相关但不含关键词的查询（例如用户说“血糖高”，但图谱里存的是“糖尿病”）。

以下是分三步走的**最简 Plan**,请在保留当前纯粹关键字检索的机制上，完成基于embedding模型的检索。

---

### 第一步：数据层改造（引入向量索引）

**目标**：让 Neo4j 支持对节点（Node）的语义搜索，而不仅仅是名字匹配。

1.1. **实现core/embed_kg.py脚本：对现有图谱注入 Embedding**：
* 调用本地 Embedding 模型，将节点的 `name` 或 `description` 处理为向量属性（ `embedding`）存储在 Neo4j 的节点上。


1.2. **在 Neo4j 中创建向量索引**：
* 在 `core/neo4j/driver.py` 或初始化脚本中，执行 Cypher 语句创建 Vector Index。
* *Cypher 示例*:
```cypher
CREATE VECTOR INDEX node_embedding_index IF NOT EXISTS
FOR (n:Entity) ON (n.embedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: 1536,
 `vector.similarity_function`: 'cosine'
}}

```





### 第二步：检索层改造（由关键词匹配改为向量检索）

**目标**：修改 `core/neo4j/query.py`，增加向量检索功能。

1. **新增 `vector_search` 方法**：
* 在 `QueryHandler` 类中增加一个函数，接受用户 Query（自然语言），将其转化为向量，然后在 Neo4j 中搜索相似节点（Top-K）。
* *代码逻辑示意*:
```python
# core/neo4j/query.py

def search_similar_entities(self, query_text, top_k=5):
    query_vector = get_embedding(query_text) # 调用你的 embedding 函数
    cypher = """
    CALL db.index.vector.queryNodes('node_embedding_index', $top_k, $query_vector)
    YIELD node, score
    RETURN node.name AS name, score
    """
    return self.driver.execute_query(cypher, query_vector=query_vector, top_k=top_k)

```





### 第三步：应用层接入（替换 Agent 中的检索逻辑）

**目标**：修改 `agents/diet/generator.py` 和 `agents/safeguard/assessor.py`，使用新的检索方法获取“锚点”，并扩展上下文。

1. **修改 `_query_dietary_by_entity` (在 `generator.py`)**：
* **原逻辑**：直接用用户 Query 中的词去图谱里 `MATCH (n {name: keyword})`。
* **新逻辑 (GraphRAG)**：
1. **Anchor Search (锚点搜索)**: 调用 `search_similar_entities(user_preference)` 找到语义最相关的 Top-5 节点（例如用户搜“想吃清淡的”，找到“低脂饮食”、“蒸菜”节点）。
2. **Graph Traversal (图遍历/上下文扩展)**: 对这 5 个锚点节点，查询它们的 **1-hop 或 2-hop** 邻居关系（例如“低脂饮食” --推荐--> “鸡胸肉”）。
3. **Context Construction**: 将检索到的 `(Head) -> [Relation] -> (Tail)` 三元组格式化为文本。




2. **代码变更点示例**：
```python
# agents/diet/generator.py 中的 _format_entity_kg_context 方法

# 旧代码：
# entity_knowledge = self.query_dietary_by_entity(user_preference) 

# 新代码 (GraphRAG 流程)：
# 1. 向量检索找到入口实体
anchors = self.kg.search_similar_entities(user_preference, top_k=3)

# 2. 扩展子图 (Retrieval)
entity_knowledge = []
for anchor in anchors:
    # 获取该实体的邻居（即 GraphRAG 中的 "Local Context"）
    neighbors = self.kg.get_neighbors(anchor['name'], hop=1) 
    entity_knowledge.extend(neighbors)

```



---

### 总结：为什么这是最简单的 Plan？

1. **不需要重构图构建流程**：目前的 `build_kg.py` 已经生成了三元组，你只需要在存储时（或者事后）“挂”上向量即可，不需要引入微软 GraphRAG 那种复杂的社区检出（Community Detection）算法。
2. **利用现有架构**：仓库已经有了 Neo4j 连接 (`core/neo4j`) 和 Agent 编排 (`agents/*`)，只需要在中间的 `query` 层做一个替换。
3. **效果立竿见影**：这种“基于向量找锚点 + 基于图结构找上下文”的方法，能直接解决 Prompt 中“用户表述与知识库实体名称不一致”的问题，是 GraphRAG 的核心价值所在。