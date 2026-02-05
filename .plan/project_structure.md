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
│   ├── build_kg.py                  # 知识图谱构建 (LLM提取)
│   ├── import_kg.py                 # 知识图谱导入Neo4j
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

## 知识图谱构建流程

### 1. 准备源文档
将文档放入 `data/` 目录，支持格式：
- PDF (.pdf)
- Word (.docx)
- Excel (.xlsx)
- 文本 (.txt)

### 2. 运行知识提取
```bash
python core/build_kg.py
```

流程：
1. 读取 `data/` 下所有文件
2. 文本清洗（移除引用、页码）
3. 按 Markdown 标题切分 chunks
4. 调用 DeepSeek LLM 提取知识三元组
5. 保存到 `output_history/Run_YYYYMMDD_HHMMSS/kg_triplets.json`

### 3. 导入 Neo4j
```bash
python core/import_kg.py
```

选项：
- 1: 从 output_history 导入（推荐）
- 2: 从指定目录导入
- 3: 显示数据库统计

### 提取的关系类型 (12种)
| 关系类型 | 说明 |
|---------|------|
| Diet_Disease | 饮食与疾病关系 |
| Food_Diet | 食物与饮食方案 |
| Food_Disease | 食物与疾病关系 |
| Amount_Food | 食物用量 |
| Frequency_Food | 食用频率 |
| Method_Food | 烹饪方式 |
| Nutrient_Disease | 营养素与疾病 |
| Restriction_Disease | 饮食禁忌 |
| Benefit_Food | 食物益处 |
| Risk_Food | 食物风险 |
| Contraindication_Food | 禁忌症 |
| Interaction_Food | 食物相互作用 |

### 当前问题
⚠️ **Schema 不匹配**: `import_kg.py` 创建通用 `Entity` 节点，但 diet generator 查询期望 `Disease`, `Food`, `Nutrient` 等特定标签。

---

## CLI 测试命令

### 前置要求
```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Neo4j (Windows)
net start Neo4j

# 配置 API Key (config.json)

# extract data and import database
python -m core.build_kg
python -m core.import_kg
```

### 统一入口 (推荐)

```bash
# 运行完整集成测试
python run.py all

# 生成饮食方案
python run.py diet --goal weight_loss

# 生成运动方案
python run.py exercise --goal weight_loss

# 运行安全评估
python run.py safeguard

# 运行完整管道
python run.py pipeline

# 带参数示例
python run.py diet --conditions diabetes,hypertension --goal weight_loss -N 3
python run.py pipeline --conditions diabetes --no-filter
```

### 独立模块测试 (Python脚本)

```python
# test_diet.py
from pipeline import generate_health_plans
result = generate_health_plans(...)
```

运行: `python test_diet.py`

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

### P1 - 服务与测试
1. **更新 FastAPI** (`core/server.py`) - 接入新架构
