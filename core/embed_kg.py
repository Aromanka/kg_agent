import sys
import os
import time
from tqdm import tqdm

# 添加项目根目录到路径，确保能导入 core 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.neo4j.driver import Neo4jClient, get_neo4j
from config_loader import get_config

# === 配置区域 ===
BATCH_SIZE = 100  # 每次处理100个节点
USE_LOCAL_MODEL = True # True使用本地模型，False使用OpenAI

# 全局 embedding 维度变量
EMBEDDING_DIM = 768  # 默认值，会在下面被覆盖

# === 初始化模型 ===
if USE_LOCAL_MODEL:
    from sentence_transformers import SentenceTransformer
    config = get_config()
    local_model_path = config.get("local_emb_path", None)

    if local_model_path and os.path.exists(local_model_path):
        print(f"正在加载本地 Embedding 模型: {local_model_path}")
        model = SentenceTransformer(local_model_path)
        # Try to get embedding dimension from model config
        EMBEDDING_DIM = model.get_sentence_embedding_dimension()
    else:
        raise ValueError("incorrect local embedding model!")

    print(f"✅ Embedding 模型加载完成，维度: {EMBEDDING_DIM}")

    def get_embedding(text):
        return model.encode(text).tolist()
else:
    from openai import OpenAI
    client = OpenAI(api_key="sk-...", base_url="...")
    EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small 默认维度

    def get_embedding(text):
        resp = client.embeddings.create(input=text, model="text-embedding-3-small")
        return resp.data[0].embedding

def main():
    # 1. 连接数据库
    client = Neo4jClient()
    print("✅ 已连接 Neo4j 数据库")

    # 2. 统计需要处理的节点总数 (假设 Label 为 Entity，且没有 embedding 属性)
    count_query = "MATCH (n:Entity) WHERE n.embedding IS NULL RETURN count(n) as total"
    result = client.query(count_query)
    total = result[0]['total']
    print(f"📊 发现 {total} 个节点需要生成 Embedding")

    if total == 0:
        print("所有节点均已有 Embedding，无需处理。")
        return

    # 3. 批量处理
    pbar = tqdm(total=total)
    
    while True:
        # 3.1 拉取一批未处理的节点
        fetch_query = """
        MATCH (n:Entity) 
        WHERE n.embedding IS NULL 
        RETURN elementId(n) as id, n.name as text 
        LIMIT $batch_size
        """
        nodes = client.query(fetch_query, batch_size=BATCH_SIZE)
        
        if not nodes:
            break

        # 3.2 计算 Embedding
        updates = []
        for node in nodes:
            text = node['text']
            # 简单的错误处理，防止空文本报错
            if not text or len(text.strip()) == 0:
                vector = [0.0] * EMBEDDING_DIM  # 占位符
            else:
                vector = get_embedding(text)
            
            updates.append({"id": node['id'], "vector": vector})

        # 3.3 批量写回 Neo4j (使用 UNWIND 语法一次性更新)
        update_query = """
        UNWIND $updates AS row
        MATCH (n) WHERE elementId(n) = row.id
        SET n.embedding = row.vector
        """
        client.query(update_query, updates=updates)
        
        pbar.update(len(nodes))

    pbar.close()
    print("✅ 所有节点 Embedding 注入完成！")

    # 4. 创建向量索引 (如果不存在)
    # 注意：vector.dimensions 必须与你使用的模型一致
    print(f"正在创建向量索引 (维度: {EMBEDDING_DIM})...")
    create_index_query = f"""
    CREATE VECTOR INDEX node_embedding_index IF NOT EXISTS
    FOR (n:Entity) ON (n.embedding)
    OPTIONS {{indexConfig: {{
     `vector.dimensions`: {EMBEDDING_DIM},
     `vector.similarity_function`: 'cosine'
    }}}}
    """
    try:
        client.query(create_index_query)
        print("✅ 向量索引 'node_embedding_index' 创建成功/已存在")
    except Exception as e:
        print(f"⚠️ 创建索引时遇到警告（可能已存在）：{e}")

if __name__ == "__main__":
    main()