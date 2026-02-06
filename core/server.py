import uvicorn
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from neo4j import GraphDatabase
from config_loader import get_config

from agents.diet.generator import generate_diet_candidates
from agents.exercise.generator import generate_exercise_candidates
from pipeline.health_pipeline import HealthPlanPipeline, generate_health_plans
from core.llm import get_unified_llm, get_llm_type

# ================= 配置加载 =================
config = get_config()

# ================= 核心逻辑 =================
driver = GraphDatabase.driver(
    config["neo4j"]["uri"],
    auth=(config["neo4j"]["username"], config["neo4j"]["password"])
)

# Initialize unified LLM
llm = get_unified_llm()
print(f"[INFO] LLM initialized in mode: {get_llm_type()}")

# ================= API 服务 =================
app = FastAPI(title="Health KG Agent API", description="基于知识图谱的健康方案生成系统")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ================= Request Models =================

class ChatReq(BaseModel):
    entity_name: str
    question: str

class DietGenerateReq(BaseModel):
    user_metadata: Dict[str, Any] = Field(..., description="用户生理数据")
    environment: Optional[Dict[str, Any]] = Field(default=None, description="环境上下文")
    user_requirement: Optional[Dict[str, Any]] = Field(default=None, description="用户需求")
    num_candidates: int = Field(default=3, ge=1, le=10, description="候选方案数量")

class ExerciseGenerateReq(BaseModel):
    user_metadata: Dict[str, Any] = Field(..., description="用户生理数据")
    environment: Optional[Dict[str, Any]] = Field(default=None, description="环境上下文")
    user_requirement: Optional[Dict[str, Any]] = Field(default=None, description="用户需求")
    num_candidates: int = Field(default=3, ge=1, le=10, description="候选方案数量")

class HealthGenerateReq(BaseModel):
    user_metadata: Dict[str, Any] = Field(..., description="用户生理数据")
    environment: Optional[Dict[str, Any]] = Field(default=None, description="环境上下文")
    user_requirement: Optional[Dict[str, Any]] = Field(default=None, description="用户需求")
    num_candidates: int = Field(default=3, ge=1, le=10, description="每种方案候选数量")
    diet_only: bool = Field(default=False, description="只生成饮食方案")
    exercise_only: bool = Field(default=False, description="只生成运动方案")
    filter_safe: bool = Field(default=True, description="是否过滤安全方案")
    min_score: int = Field(default=60, ge=0, le=100, description="最低安全分数")

# ================= Chat/KG Endpoints (Legacy) =================

def extract_keywords(question):
    """提取关键词"""
    try:
        return llm.extract_keywords(question, max_count=3)
    except Exception as e:
        print(f"[ERROR] extract_keywords failed: {e}")
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
        validation = llm.chat(
            messages=[{"role": "user", "content": prompt_check}],
            temperature=0.1
        ).strip()

        if "PASS" in validation.upper():
            return initial_reply
        else:
            print(f"触发修正，原因: {validation}")
            # 修正
            prompt_fix = f"""
            你之前的回答有误。请根据事实和错误提示重新回答。
            问题：{question}
            事实：{kg_data}
            错误：{validation}
            请输出修正后的准确回答。
            """
            fix_resp = llm.chat(
                messages=[{"role": "user", "content": prompt_fix}],
                temperature=0.5
            )
            return fix_resp + "\n\n(注：本回答已通过知识图谱自动修正)"
    except Exception as e:
        print(f"[ERROR] validate_and_correct failed: {e}")
        return initial_reply


@app.post("/api/chat")
def chat_endpoint(req: ChatReq):
    """知识图谱问答"""
    print(f"用户提问: {req.question}")
    keywords = extract_keywords(req.question)
    if req.entity_name and req.entity_name not in keywords: keywords.append(req.entity_name)

    kg_context = search_kg(keywords)

    # 初次回答
    system_prompt = f"基于以下事实回答，必须引用数值。事实：\n{kg_context}"
    try:
        draft = llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.question}
            ]
        )

        # 验证并修正
        final_reply = validate_and_correct(kg_context, req.question, draft)
        return {"reply": final_reply}

    except Exception as e:
        print(f"Error: {e}")
        return {"reply": "服务器繁忙，请重试"}


@app.get("/api/graph")
def graph_endpoint(entity_name: str):
    """获取实体关系图"""
    with driver.session() as session:
        q = """
        MATCH (n)-[r]-(m)
        WHERE toLower(n.name) CONTAINS toLower($n)
        RETURN n.name as source_name, m.name as target_name,
               type(r) as rel_type, r.amount as a, r.unit as u
        LIMIT 1000
        """
        res = session.run(q, n=entity_name)
        nodes, links = {}, []
        for rec in res:
            s = rec['source_name']
            t = rec['target_name']
            s_cat = 0 if entity_name.lower() in s.lower() else 1
            t_cat = 0 if entity_name.lower() in t.lower() else 1

            # Debug: print actual rel_type
            rel_type_val = rec['rel_type']
            print(f"[DEBUG] Relationship: {s} -[{rel_type_val}]-> {t}")

            # Use lowercase 'name' for frontend compatibility
            nodes[s] = {"name": s, "category": s_cat, "symbolSize": 50 if s_cat == 0 else 30}
            nodes[t] = {"name": t, "category": t_cat, "symbolSize": 50 if t_cat == 0 else 30}

            # Build edge label
            label = rel_type_val
            if rec['a']: label += f"\n{rec['a']}{rec['u']}"
            links.append({"source": s, "target": t, "value": label})

        print(f"[DEBUG] Total nodes: {len(nodes)}, links: {len(links)}")
        return {"nodes": list(nodes.values()), "links": links}


# ================= Diet Endpoints =================

@app.post("/api/diet/generate")
def diet_generate_endpoint(req: DietGenerateReq):
    """饮食方案生成API"""
    print(f"饮食方案生成请求: metadata={req.user_metadata}")
    try:
        result = generate_diet_candidates(
            user_metadata=req.user_metadata,
            environment=req.environment,
            user_requirement=req.user_requirement,
            num_candidates=req.num_candidates
        )
        return {
            "status": "success",
            "candidates": [c.model_dump() for c in result],
            "count": len(result)
        }
    except Exception as e:
        print(f"饮食生成失败: {e}")
        return {"status": "error", "error": "饮食方案生成失败", "detail": str(e)}


@app.post("/api/diet/init_db")
def diet_init_db_endpoint():
    """初始化食物数据库到Neo4j"""
    try:
        from agents.diet.generator import init_food_database_in_kg
        init_food_database_in_kg()
        return {"status": "success", "message": "食物数据库已初始化"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ================= Exercise Endpoints =================

@app.post("/api/exercise/generate")
def exercise_generate_endpoint(req: ExerciseGenerateReq):
    """运动方案生成API"""
    print(f"运动方案生成请求: metadata={req.user_metadata}")
    try:
        result = generate_exercise_candidates(
            user_metadata=req.user_metadata,
            environment=req.environment,
            user_requirement=req.user_requirement,
            num_candidates=req.num_candidates
        )
        return {
            "status": "success",
            "candidates": [c.model_dump() for c in result],
            "count": len(result)
        }
    except Exception as e:
        print(f"运动生成失败: {e}")
        return {"status": "error", "error": "运动方案生成失败", "detail": str(e)}


# ================= Health Pipeline Endpoints =================

@app.post("/api/health/generate")
def health_generate_endpoint(req: HealthGenerateReq):
    """健康方案生成API (饮食+运动+安全评估)"""
    print(f"健康方案生成请求: goal={req.user_requirement}")
    try:
        result = generate_health_plans(
            user_metadata=req.user_metadata,
            environment=req.environment,
            user_requirement=req.user_requirement,
            num_candidates=req.num_candidates,
            diet_only=req.diet_only,
            exercise_only=req.exercise_only,
            filter_safe=req.filter_safe,
            min_score=req.min_score
        )
        return {
            "status": "success",
            "diet_candidates": result.get("diet_candidates", []),
            "exercise_candidates": result.get("exercise_candidates", []),
            "diet_assessments": result.get("diet_assessments", {}),
            "exercise_assessments": result.get("exercise_assessments", {}),
            "combined_assessment": result.get("combined_assessment", {}),
            "generated_at": result.get("generated_at")
        }
    except Exception as e:
        print(f"健康方案生成失败: {e}")
        return {"status": "error", "error": "健康方案生成失败", "detail": str(e)}


@app.get("/api/health/assessments")
def get_assessments_endpoint(plan_type: str = "all"):
    """获取评估信息"""
    return {"status": "placeholder", "message": "评估详情查询功能待实现"}


# ================= LLM Status Endpoint =================

@app.get("/api/llm/status")
def llm_status_endpoint():
    """获取当前 LLM 模式状态"""
    return {
        "llm_type": get_llm_type(),
        "is_local": llm.is_local,
        "local_model_path": config.get("local_model_path"),
        "api_model": config.get("deepseek", {}).get("model", "deepseek-chat")
    }


@app.post("/api/llm/reload")
def llm_reload_endpoint(mode: str = None):
    """
    重新加载 LLM 模式

    Args:
        mode: 'local' | 'api' | None (use config)
    """
    if mode == "local":
        llm.reload(force_local=True)
    elif mode == "api":
        llm.reload(force_local=False)
    else:
        llm.reload()

    return {
        "status": "success",
        "llm_type": get_llm_type(),
        "message": f"LLM reloaded in mode: {get_llm_type()}"
    }


# ================= Web UI =================

@app.get("/", response_class=HTMLResponse)
def root():
    """Web UI入口"""
    with open("kg/templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


# ================= Main =================

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
