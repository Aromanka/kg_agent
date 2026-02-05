"""
Import knowledge graph data from JSON/CSV files into Neo4j database.
Run after build_kg_deepseek.py has generated the output files.
"""
import os
import json
import glob
from neo4j import GraphDatabase

# ================= 配置加载 =================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

NEO4J_URI = config["neo4j"]["uri"]
NEO4J_AUTH = (config["neo4j"]["username"], config["neo4j"]["password"])

# 数据来源目录 (build_kg_deepseek.py 的输出目录)
OUTPUT_HISTORY_DIR = "output_history"
INPUT_DIR = "data"  # 也支持直接导入原始文件

# ================= 核心逻辑 =================
driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)


def create_indexes(session):
    """创建索引以加速查询"""
    indexes = [
        "CREATE FULLTEXT INDEX search_index IF NOT EXISTS FOR (n:Entity) ON EACH [n.name]",
        "CREATE INDEX entity_name_idx IF NOT EXISTS FOR (n:Entity) ON (n.name)",
    ]
    for idx in indexes:
        try:
            session.run(idx)
        except Exception as e:
            print(f"索引创建跳过或失败: {e}")


def clear_database(session):
    """清空数据库中的现有数据（谨慎使用）"""
    confirm = input("警告：这将删除所有现有数据。是否继续？(y/n): ")
    if confirm.lower() != 'y':
        print("已取消")
        return False
    session.run("MATCH (n) DETACH DELETE n")
    print("已清空数据库")
    return True


def import_json_triplets(session, json_path):
    """从JSON文件导入三元组"""
    print(f"📄 正在导入: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        triplets = json.load(f)

    if not triplets:
        print(f"  ⚠️ 空文件，跳过")
        return 0

    count = 0
    for t in triplets:
        head = t.get('head', '').strip()
        relation = t.get('relation', '').strip()
        tail = t.get('tail', '').strip()
        source = t.get('source', '')

        if not head or not relation or not tail:
            continue

        try:
            # 创建实体和关系
            session.run("""
                MERGE (h:Entity {name: $head})
                MERGE (t:Entity {name: $tail})
                MERGE (h)-[r:RELATION {type: $relation, source: $source}]->(t)
            """, head=head, tail=tail, relation=relation, source=source)
            count += 1
        except Exception as e:
            print(f"  ❌ 导入失败: {head} -[{relation}]-> {tail}: {e}")

    print(f"  ✅ 成功导入 {count} 条关系")
    return count


def import_csv_triplets(session, csv_path):
    """从CSV文件导入三元组"""
    import pandas as pd

    print(f"📄 正在导入CSV: {csv_path}")

    df = pd.read_csv(csv_path)
    if df.empty:
        print(f"  ⚠️ 空文件，跳过")
        return 0

    count = 0
    for _, row in df.iterrows():
        head = str(row.get('head', '')).strip()
        relation = str(row.get('relation', '')).strip()
        tail = str(row.get('tail', '')).strip()
        source = str(row.get('source', '')).strip()

        if not head or not relation or not tail or head == 'nan':
            continue

        try:
            session.run("""
                MERGE (h:Entity {name: $head})
                MERGE (t:Entity {name: $tail})
                MERGE (h)-[r:RELATION {type: $relation, source: $source}]->(t)
            """, head=head, tail=tail, relation=relation, source=source)
            count += 1
        except Exception as e:
            print(f"  ❌ 导入失败: {head} -[{relation}]-> {tail}: {e}")

    print(f"  ✅ 成功导入 {count} 条关系")
    return count


def import_from_output_history(session):
    """从 output_history 目录导入所有数据"""
    if not os.path.exists(OUTPUT_HISTORY_DIR):
        print(f"⚠️ 目录不存在: {OUTPUT_HISTORY_DIR}")
        return 0

    json_files = glob.glob(os.path.join(OUTPUT_HISTORY_DIR, "**/*.json"), recursive=True)
    csv_files = glob.glob(os.path.join(OUTPUT_HISTORY_DIR, "**/*.csv"), recursive=True)

    total = 0
    for json_file in json_files:
        total += import_json_triplets(session, json_file)

    for csv_file in csv_files:
        total += import_csv_triplets(session, csv_file)

    return total


def import_from_directory(session, directory):
    """从指定目录导入文档直接解析（需要先运行LLM提取）"""
    # 如果目录下有已提取的三元组文件
    json_files = glob.glob(os.path.join(directory, "*.json"))
    csv_files = glob.glob(os.path.join(directory, "*.csv"))

    total = 0
    for json_file in json_files:
        total += import_json_triplets(session, json_file)

    for csv_file in csv_files:
        total += import_csv_triplets(session, csv_file)

    return total


def show_stats(session):
    """显示数据库统计信息"""
    print("\n📊 数据库统计:")

    # 实体数量
    result = session.run("MATCH (n:Entity) RETURN count(n) as count")
    entity_count = result.single()["count"]
    print(f"  实体数量: {entity_count}")

    # 关系数量
    result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
    rel_count = result.single()["count"]
    print(f"  关系数量: {rel_count}")

    # 关系类型分布
    print("  关系类型分布:")
    result = session.run("""
        MATCH ()-[r]->()
        RETURN r.type as type, count(r) as count
        ORDER BY count DESC
    """)
    for record in result:
        print(f"    {record['type']}: {record['count']}")


def main():
    print("=" * 50)
    print("Neo4j 知识图谱导入工具")
    print("=" * 50)

    with driver.session() as session:
        # 选项菜单
        print("\n选择导入模式:")
        print("1. 从 output_history 导入 (build_kg_deepseek.py 的输出)")
        print("2. 从指定目录导入")
        print("3. 显示数据库统计")
        print("4. 清空数据库并退出")

        choice = input("\n请选择 (1-4): ").strip()

        if choice == "1":
            create_indexes(session)
            total = import_from_output_history(session)
            print(f"\n🎉 总计导入 {total} 条关系")
            show_stats(session)

        elif choice == "2":
            directory = input("请输入目录路径: ").strip()
            if os.path.exists(directory):
                create_indexes(session)
                total = import_from_directory(session, directory)
                print(f"\n🎉 总计导入 {total} 条关系")
                show_stats(session)
            else:
                print(f"❌ 目录不存在: {directory}")

        elif choice == "3":
            show_stats(session)

        elif choice == "4":
            if clear_database(session):
                print("数据库已清空")

        else:
            print("无效选择")


if __name__ == "__main__":
    main()
