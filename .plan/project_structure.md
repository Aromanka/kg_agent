# 项目结构设计

## 整体架构 (Three-Agent Architecture)

```
kg_agents/
├── agents/                          # [NEW] 三种Agent实现
│   ├── __init__.py
│   ├── base.py                      # Agent基类 (待实现)
│   ├── diet/                        # [NEW] 饮食Agent
│   │   ├── __init__.py
│   │   ├── generator.py            # 饮食方案生成器 (从kg/diet_generator.py移动)
│   │   ├── prompts.py              # 饮食Prompt模板 (从kg/prompts/diet_kg.py移动)
│   │   └── models.py                # 饮食Pydantic模型
│   ├── exercise/                   # [NEW] 运动Agent (待实现)
│   │   ├── __init__.py
│   │   ├── generator.py             # 运动方案生成器
│   │   └── models.py                # 运动Pydantic模型
│   └── safeguard/                   # [NEW] 风险评估Agent (待实现)
│       ├── __init__.py
│       ├── assessor.py              # 安全评估器
│       └── models.py                # 评估模型
│
├── core/                            # [NEW] 核心服务层 (原kg/核心功能)
│   ├── __init__.py
│   ├── server.py                    # FastAPI服务 (原kg/server_local.py)
│   ├── neo4j/                       # Neo4j数据库工具
│   │   ├── __init__.py
│   │   ├── driver.py                # 数据库连接驱动
│   │   └── query.py                  # 通用查询工具
│   └── llm/                         # LLM客户端封装
│       ├── __init__.py
│       └── client.py                 # OpenAI/DeepSeek客户端
│
├── scripts/                         # [NEW] 基础设施脚本 (待创建)
│   ├── __init__.py
│   ├── build_kg.py                  # 知识图谱构建器 (原kg/build_kg_deepseek.py)
│   └── import_kg.py                 # 数据导入工具 (原kg/build_neo4j_database.py)
│
├── data/                            # 数据目录
│   └── (PDF/DOCX/Excel源文档)
│
├── pipeline/                        # 管道编排 (待实现)
│   ├── __init__.py
│   └── health_pipeline.py           # 主流程编排
│
├── tests/                           # [NEW] 测试目录 (原kg/test/)
│   ├── __init__.py
│   └── test_read.py
│
├── .doc/                            # 文档资料
│   └── neo4j.md
│
├── config.json                      # API密钥和配置
├── requirements.txt                 # Python依赖
├── CLAUDE.md                        # Claude Code指导文件
└── .plan/                           # 项目规划
    ├── targets.md
    └── project_structure.md         # 本文件
```

---

## 文件迁移清单 (TODO)

| 文件 | 当前路径 | 目标路径 | 状态 |
|------|----------|----------|------|
| diet_generator.py | `kg/diet_generator.py` | `agents/diet/generator.py` | ⏳ 待移动 |
| diet_kg.py (prompts) | `kg/prompts/diet_kg.py` | `agents/diet/prompts.py` | ⏳ 待移动 |
| server_local.py | `kg/server_local.py` | `core/server.py` | ⏳ 待移动 |
| build_kg_deepseek.py | `kg/build_kg_deepseek.py` | `scripts/build_kg.py` | ⏳ 待移动 |
| build_neo4j_database.py | `kg/build_neo4j_database.py` | `scripts/import_kg.py` | ⏳ 待移动 |
| test_read.py | `kg/test/test_read.py` | `tests/test_read.py` | ⏳ 待移动 |
| __init__.py (kg) | `kg/__init__.py` | 删除/保留 | ⏳ 待定 |
| prompts/__init__.py | `kg/prompts/__init__.py` | 删除 | ⏳ 待删除 |

**待创建的新文件**:
- `agents/base.py` - Agent基类
- `agents/diet/models.py` - 饮食Pydantic模型
- `agents/exercise/generator.py` - 运动生成器
- `agents/exercise/models.py` - 运动模型
- `agents/safeguard/assessor.py` - 安全评估器
- `agents/safeguard/models.py` - 评估模型
- `core/neo4j/driver.py` - Neo4j驱动
- `core/neo4j/query.py` - 查询工具
- `core/llm/client.py` - LLM客户端
- `scripts/__init__.py` - 脚本模块

---

## 文件清理清单

| 文件/目录 | 操作 | 原因 |
|----------|------|------|
| `kg/prompts/` | 删除 | 迁移到 `agents/diet/prompts.py` |
| `kg/test/` | 删除 | 迁移到 `tests/` |
| `kg/__init__.py` | 评估 | 可能需要保留导入兼容性 |
| `.plan/bug_to_fix.md` | 评估 | 检查是否需要保留 |

---

## 三种Agent职责

### 1. Diet Agent (`agents/diet/`)
- **输入**: user_metadata + environment + user_requirement
- **输出**: 饮食候选方案列表
- **依赖**: 饮食知识图谱

### 2. Exercise Agent (`agents/exercise/`)
- **输入**: user_metadata + environment + user_requirement
- **输出**: 运动候选方案列表
- **依赖**: 运动知识图谱

### 3. Safeguard Agent (`agents/safeguard/`)
- **输入**: plan + user_metadata + environment
- **输出**: {0-100分安全评分, True/False判断}
- **功能**: 禁忌检索、规则引擎、LLM语义评估

---

## 当前进度

| Milestone | 任务 | 状态 |
|-----------|------|------|
| M1 | Diet Agent 重构 (LLM-based) | ✅ 已完成 |
| M2 | 目录结构重构 | ⏳ 进行中 |
| M3 | Exercise Agent | ⏳ 待实现 |
| M4 | Safeguard Agent | ⏳ 待实现 |
| M5 | Pipeline Integration | ⏳ 待实现 |

---

## 下一步任务

### Step 1: 目录结构创建
```bash
mkdir -p agents/diet agents/exercise agents/safeguard
mkdir -p core/neo4j core/llm scripts tests
```

### Step 2: 文件迁移
1. 创建 `agents/diet/__init__.py`, `prompts.py`, `models.py`
2. 移动 `kg/diet_generator.py` → `agents/diet/generator.py`
3. 移动 `kg/prompts/diet_kg.py` → `agents/diet/prompts.py`
4. 创建 `core/server.py`，迁移 `kg/server_local.py`
5. 迁移基础设施脚本到 `scripts/`

### Step 3: 清理
- 删除空目录 `kg/prompts/`, `kg/test/`
- 更新导入路径
