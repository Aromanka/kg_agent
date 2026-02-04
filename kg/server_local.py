import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from neo4j import GraphDatabase
from openai import OpenAI
import json
import os
from diet_generator import generate_diet_candidates

# ================= 配置加载 =================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

NEO4J_URI = config["neo4j"]["uri"]
NEO4J_AUTH = (config["neo4j"]["username"], config["neo4j"]["password"])
DEEPSEEK_API_KEY = config["deepseek"]["api_key"]
DEEPSEEK_BASE_URL = config["deepseek"]["base_url"]

# ================= 核心逻辑 =================
driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def extract_keywords(question):
    """提取关键词"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": f"提取用户问题中的1-3个医学实体关键词，只返回JSON列表，如['Apple']。问题：{question}"}],
            temperature=0.1
        )
        return json.loads(resp.choices[0].message.content.strip())
    except:
        return []

def search_kg(keywords):
    """全库检索"""
    data = []
    with driver.session() as session:
        for word in keywords:
            try:
                # 尝试全文索引
                query = """
                CALL db.index.fulltext.queryNodes("search_index", $word) YIELD node, score
                WHERE score > 0.6
                MATCH (node)-[r]-(m)
                RETURN node.name as h, r.type as rel_type, m.name as t, r.amount as a, r.unit as u
                LIMIT 15
                """
                res = session.run(query, word=f"{word}~")
                for rec in res:
                    info = f"{rec['h']} -[{rec['rel_type']}]-> {rec['t']}"
                    if rec['a'] and rec['u']: info += f" (数值:{rec['a']}{rec['u']})"
                    data.append(info)
            except:
                pass
    return "\n".join(list(set(data))) if data else "暂无直接关联数据"

def validate_and_correct(kg_data, question, initial_reply):
    """验证并修正"""
    if "暂无" in kg_data: return initial_reply
    
    # 验证
    prompt_check = f"""
    作为医学核查员，检查【AI回答】是否与【图谱事实】有严重数值或逻辑冲突。
    事实：{kg_data}
    回答：{initial_reply}
    若有冲突，指出错误；否则输出 PASS。
    """
    try:
        check_resp = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt_check}], temperature=0.1
        )
        validation = check_resp.choices[0].message.content.strip()
        
        if "PASS" in validation.upper():
            return initial_reply
        else:
            print(f"🔄 触发修正，原因: {validation}")
            # 修正
            prompt_fix = f"""
            你之前的回答有误。请根据事实和错误提示重新回答。
            问题：{question}
            事实：{kg_data}
            错误：{validation}
            请输出修正后的准确回答。
            """
            fix_resp = client.chat.completions.create(
                model="deepseek-chat", messages=[{"role": "user", "content": prompt_fix}], temperature=0.5
            )
            return fix_resp.choices[0].message.content + "\n\n*(注：本回答已通过知识图谱自动修正)*"
    except:
        return initial_reply

# ================= API 服务 =================
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatReq(BaseModel):
    entity_name: str
    question: str

class DietGenerateReq(BaseModel):
    user_metadata: Dict[str, Any]
    environment: Optional[Dict[str, Any]] = None
    user_requirement: Optional[Dict[str, Any]] = None
    num_candidates: int = 3
    sampling_strategy: str = "balanced"

@app.post("/api/chat")
def chat_endpoint(req: ChatReq):
    print(f"用户提问: {req.question}")
    keywords = extract_keywords(req.question)
    if req.entity_name and req.entity_name not in keywords: keywords.append(req.entity_name)
    
    kg_context = search_kg(keywords)
    
    # 初次回答
    system_prompt = f"基于以下事实回答，必须引用数值。事实：\n{kg_context}"
    try:
        draft = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": req.question}]
        ).choices[0].message.content
        
        # 验证并修正
        final_reply = validate_and_correct(kg_context, req.question, draft)
        return {"reply": final_reply}
        
    except Exception as e:
        print(f"Error: {e}")
        return {"reply": "服务器繁忙，请重试"}

@app.get("/api/graph")
def graph_endpoint(entity_name: str):
    with driver.session() as session:
        # 查询 - 使用 r.type 获取实际关系类型，而非 type(r) 获取关系类型名
        q = "MATCH (n:Entity)-[r]-(m) WHERE toLower(n.name) CONTAINS toLower($n) RETURN n.name as s, m.name as t, r.type as rel_type, r.amount as a, r.unit as u LIMIT 1000"
        res = session.run(q, n=entity_name)
        nodes, links = {}, []
        for rec in res:
            s, t = rec['s'], rec['t']
            s_cat = 0 if entity_name.lower() in s.lower() else 1
            t_cat = 0 if entity_name.lower() in t.lower() else 1
            nodes[s] = {"name": s, "category": s_cat, "symbolSize": 50 if s_cat==0 else 30}
            nodes[t] = {"name": t, "category": t_cat, "symbolSize": 50 if t_cat==0 else 30}

            label = rec['rel_type']
            if rec['a']: label += f"\n{rec['a']}{rec['u']}"
            links.append({"source": s, "target": t, "value": label})

        return {"nodes": list(nodes.values()), "links": links}

@app.post("/api/diet/generate")
def diet_generate_endpoint(req: DietGenerateReq):
    """饮食方案生成API"""
    print(f"饮食方案生成请求: metadata={req.user_metadata}")
    try:
        result = generate_diet_candidates(
            user_metadata=req.user_metadata,
            environment=req.environment,
            user_requirement=req.user_requirement,
            num_candidates=req.num_candidates,
            sampling_strategy=req.sampling_strategy
        )
        return result
    except Exception as e:
        print(f"饮食生成失败: {e}")
        return {"error": "饮食方案生成失败", "detail": str(e)}


@app.post("/api/diet/init_db")
def diet_init_db_endpoint():
    """初始化食物数据库到Neo4j"""
    try:
        from diet_generator import init_food_database_in_kg
        init_food_database_in_kg()
        return {"status": "success", "message": "食物数据库已初始化"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/", response_class=HTMLResponse)
def root():
    # 读取同目录下的 templates/index.html
    with open("kg/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)