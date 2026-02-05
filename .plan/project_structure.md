# 项目结构设计

## 整体架构 (Three-Agent Architecture)

```
kg_agents/
├── agents/                          # 三种Agent实现
│   ├── base.py                      # Agent基类 ✅
│   ├── diet/                        # 饮食Agent ✅
│   │   ├── __init__.py
│   │   ├── generator.py             # 饮食生成器 ✅
│   │   ├── prompts.py               # Prompt模板
│   │   └── models.py                # Pydantic模型 ✅
│   ├── exercise/                    # 运动Agent ✅
│   │   ├── __init__.py
│   │   ├── generator.py             # 运动生成器 ✅
│   │   └── models.py                # Pydantic模型 ✅
│   └── safeguard/                   # 风险评估Agent ✅
│       ├── __init__.py
│       ├── assessor.py               # 安全评估器 ✅
│       └── models.py                # Pydantic模型 ✅
│
├── core/                            # 核心服务层 ✅
│   ├── __init__.py
│   ├── server.py                    # FastAPI服务
│   ├── neo4j/
│   │   ├── __init__.py
│   │   ├── driver.py                # Neo4j驱动 ✅
│   │   └── query.py                 # KG查询工具 ✅
│   └── llm/
│       ├── __init__.py
│       └── client.py                # LLM客户端 ✅
│
├── pipeline/                         # 管道编排 ✅
│   ├── __init__.py
│   └── health_pipeline.py           # HealthPlanPipeline ✅
│
├── scripts/                         # 基础设施脚本
│   ├── __init__.py
│   ├── build_kg.py
│   └── import_kg.py
│
├── data/
├── tests/
│   ├── __init__.py
│   └── test_read.py
│
├── .doc/
│   └── neo4j.md
│
├── config.json
├── requirements.txt
├── CLAUDE.md
└── .plan/
    ├── targets.md
    └── project_structure.md         # 本文件
```

---

## 当前进度总结

### ✅ 已完成

| 模块 | 组件 | 文件 | 状态 |
|------|------|------|------|
| **Core** | LLM客户端 | `core/llm/client.py` | ✅ |
| | Neo4j驱动 | `core/neo4j/driver.py` | ✅ |
| | KG查询工具 | `core/neo4j/query.py` | ✅ |
| **Agents Base** | Agent基类 | `agents/base.py` | ✅ |
| **Diet Agent** | 生成器 | `agents/diet/generator.py` | ✅ |
| | 模型 | `agents/diet/models.py` | ✅ |
| **Exercise Agent** | 生成器 | `agents/exercise/generator.py` | ✅ |
| | 模型 | `agents/exercise/models.py` | ✅ |
| **Safeguard Agent** | 评估器 | `agents/safeguard/assessor.py` | ✅ |
| | 模型 | `agents/safeguard/models.py` | ✅ |
| **Pipeline** | 编排器 | `pipeline/health_pipeline.py` | ✅ |

### ⏳ 待实现

| 组件 | 文件 | 优先级 |
|------|------|--------|
| FastAPI整合 | `core/server.py` | P1 |
| 编写测试 | `tests/` | P1 |

---

## CLI 测试命令

### 前置要求
```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Neo4j (Windows)
net start Neo4j

# 配置 API Key (config.json)
```

### 测试命令

#### 1. 测试饮食生成器
```bash
python -m agents.diet.generator
```

#### 2. 测试运动生成器
```bash
python -m agents.exercise.generator
```

#### 3. 测试安全评估器
```bash
python -m agents.safeguard.assessor
```

#### 4. 测试完整 Pipeline
```bash
python -m pipeline.health_pipeline
```

#### 5. 集成测试 (Python脚本)
```python
# test_integration.py
from pipeline import generate_health_plans

test_input = {
    "user_metadata": {
        "age": 35,
        "gender": "male",
        "height_cm": 175,
        "weight_kg": 70,
        "medical_conditions": ["diabetes"],
        "dietary_restrictions": ["low_sodium"],
        "fitness_level": "intermediate"
    },
    "environment": {
        "weather": {"condition": "clear", "temperature_c": 25},
        "time_context": {"season": "summer"}
    },
    "user_requirement": {
        "goal": "weight_loss",
        "intensity": "moderate"
    },
    "num_candidates": 2,
    "filter_safe": True,
    "min_score": 60
}

result = generate_health_plans(**test_input)
print(f"Diet candidates: {len(result['diet_candidates'])}")
print(f"Exercise candidates: {len(result['exercise_candidates'])}")
print(f"Overall score: {result['combined_assessment']['overall_score']}")
```

运行: `python test_integration.py`

---

## 快速使用示例

```python
from pipeline import generate_health_plans

# 1. 准备输入
input_data = {
    "user_metadata": {
        "age": 35,
        "gender": "male",
        "height_cm": 175,
        "weight_kg": 70,
        "medical_conditions": ["diabetes"],
        "dietary_restrictions": ["low_sodium"],
        "fitness_level": "intermediate"
    },
    "environment": {
        "weather": {"condition": "clear", "temperature_c": 25},
        "time_context": {"season": "summer"}
    },
    "user_requirement": {
        "goal": "weight_loss",
        "intensity": "moderate"
    },
    "num_candidates": 3
}

# 2. 生成健康计划
result = generate_health_plans(**input_data)

# 3. 查看结果
print(f"饮食候选数: {len(result['diet_candidates'])}")
print(f"运动候选数: {len(result['exercise_candidates'])}")
print(f"综合评分: {result['combined_assessment']['overall_score']}/100")
print(f"是否安全: {result['combined_assessment']['is_safe']}")
```

---

## 三种Agent职责

| Agent | 输入 | 输出 |
|-------|------|------|
| Diet | user_metadata + env + requirement | 饮食候选 (含营养素) |
| Exercise | user_metadata + env + requirement | 运动候选 (含卡路里) |
| Safeguard | plan + user_metadata + env | {0-100分, is_safe, 风险因素} |

---

## 下一步任务

### P1 - 服务与测试
1. **更新 FastAPI** (`core/server.py`) - 接入新架构
2. **编写测试** (`tests/`) - 单元测试 + 集成测试
