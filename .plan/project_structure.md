# 项目结构设计

## 整体架构 (Three-Agent Architecture)

```
kg_agents/
├── agents/                          # 三种Agent实现
│   ├── base.py                      # Agent基类 + Mixins
│   ├── diet/                        # 饮食Agent
│   │   ├── __init__.py
│   │   ├── generator.py             # DietAgent生成器
│   │   ├── prompts.py              # Prompt模板
│   │   └── models.py               # Pydantic模型
│   ├── exercise/                    # 运动Agent
│   │   ├── __init__.py
│   │   ├── generator.py             # ExerciseAgent生成器
│   │   └── models.py               # Pydantic模型
│   └── safeguard/                  # 风险评估Agent
│       ├── __init__.py
│       ├── assessor.py              # SafeguardAgent评估器
│       └── models.py                # Pydantic模型
│
├── core/                            # 核心服务层
│   ├── __init__.py
│   ├── server.py                   # FastAPI服务
│   ├── build_kg.py                 # 知识图谱构建 (LLM提取)
│   ├── import_kg.py                # 知识图谱导入Neo4j
│   ├── neo4j/
│   │   ├── __init__.py
│   │   ├── driver.py               # Neo4j驱动
│   │   └── query.py                # KG查询工具
│   └── llm/
│       ├── __init__.py
│       └── client.py                # LLM客户端
│
├── pipeline/                       # 管道编排
│   ├── __init__.py
│   └── health_pipeline.py          # HealthPlanPipeline
│
├── data/
│   ├── diet/                       # 饮食知识文档
│   └── exer/                       # 运动知识文档
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
    └── project_structure.md
```

---

## 当前进度总结

### 已完成 ✅

| 模块 | 组件 | 文件 | 状态 |
|------|------|------|------|
| **Core** | LLM客户端 | `core/llm/client.py` | ✅ |
| | Neo4j驱动 | `core/neo4j/driver.py` | ✅ |
| | KG查询工具 | `core/neo4j/query.py` | ✅ |
| | FastAPI服务 | `core/server.py` | ✅ |
| | KG构建工具 | `core/build_kg.py` | ✅ |
| | KG导入工具 | `core/import_kg.py` | ✅ |
| **Base** | Agent基类 | `agents/base.py` | ✅ |
| **Diet Agent** | 生成器 | `agents/diet/generator.py` | ✅ |
| | 模型 | `agents/diet/models.py` | ✅ |
| | Prompt模板 | `agents/diet/prompts.py` | ✅ |
| **Exercise Agent** | 生成器 | `agents/exercise/generator.py` | ✅ |
| | 模型 | `agents/exercise/models.py` | ✅ |
| **Safeguard Agent** | 评估器 | `agents/safeguard/assessor.py` | ✅ |
| | 模型 | `agents/safeguard/models.py` | ✅ |
| **Pipeline** | 编排器 | `pipeline/health_pipeline.py` | ✅ |

---

## 知识图谱构建流程

### 1. 准备源文档
将文档放入 `data/` 目录，支持格式：
- PDF (.pdf)
- Word (.docx)
- Excel (.xlsx)
- 文本 (.txt)

**目录结构**：
```
data/
├── diet/          # 饮食知识文档
│   ├── nutrition_guide.pdf
│   └── diabetes_diet.docx
└── exer/          # 运动知识文档
    └── exercise_guide.pdf
```

### 2. 运行知识提取
```bash
# 默认同时构建饮食和运动 KG
python -m core.build_kg

# 只构建饮食 KG
python -m core.build_kg --kg=diet

# 只构建运动 KG
python -m core.build_kg --kg=exercise
```

流程：
1. 读取 `data/diet/` 或 `data/exer/` 下所有文件
2. 文本清洗（移除引用、页码）
3. 按 Markdown 标题切分 chunks
4. 调用 DeepSeek LLM 提取知识三元组
5. 保存到 `output_history/Diet_YYYYMMDD_HHMMSS/` 或 `output_history/Exercise_...`

### 3. 导入 Neo4j
```bash
python -m core.import_kg
```

选项：
- 1: 从 output_history 导入（推荐）
- 2: 从指定目录导入
- 3: 显示数据库统计
- 4: 清空数据库

---

## 提取的关系类型

### 饮食 KG (12种)
| 关系类型 | 说明 |
|---------|------|
| Target_Recommendation | 针对特定人群的推荐 |
| Target_Avoid | 针对特定人群的禁忌 |
| Disease_Management | 饮食对疾病的管理作用 |
| Nutrient_Content | 食物营养成分 |
| Has_Benefit | 摄入带来的益处 |
| Has_Risk | 摄入可能导致的风险 |
| Recommended_Intake | 推荐摄入量 |
| Recommended_Freq | 推荐摄入频率 |
| Max_Limit | 建议上限 |
| Preparation_Method | 烹饪方式 |
| Interaction | 食物相互作用 |
| Substitute_With | 替代方案 |

### 运动 KG (12种)
| 关系类型 | 说明 |
|---------|------|
| Target_Recommendation | 针对特定人群的推荐 |
| Target_Avoid | 针对特定人群的禁忌 |
| Disease_Management | 运动对疾病的管理作用 |
| Targets_Muscle | 运动针对的肌肉群 |
| Has_Benefit | 运动的益处 |
| Has_Risk | 运动的风险 |
| Recommended_Duration | 推荐时长 |
| Recommended_Freq | 推荐频率 |
| Max_Limit | 建议上限 |
| Technique_Method | 运动技巧 |
| Interaction | 运动相互作用 |
| Substitute_With | 替代运动 |

---

## API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/chat` | POST | 知识图谱问答 |
| `/api/graph` | GET | 获取实体关系图 |
| `/api/diet/generate` | POST | 饮食方案生成 |
| `/api/exercise/generate` | POST | 运动方案生成 |
| `/api/health/generate` | POST | 健康方案生成（饮食+运动+安全评估） |
| `/api/diet/init_db` | POST | 初始化食物数据库 |

### 请求示例

**饮食生成**：
```json
POST /api/diet/generate
{
    "user_metadata": {
        "age": 35,
        "gender": "male",
        "height_cm": 175,
        "weight_kg": 70,
        "medical_conditions": ["diabetes"],
        "fitness_level": "intermediate"
    },
    "environment": {"time_context": {"season": "summer"}},
    "user_requirement": {"goal": "weight_loss"},
    "num_candidates": 3
}
```

**运动生成**：
```json
POST /api/exercise/generate
{
    "user_metadata": {...},
    "user_requirement": {"goal": "weight_loss", "intensity": "moderate"},
    "num_candidates": 3
}
```

**健康方案（完整管道）**：
```json
POST /api/health/generate
{
    "user_metadata": {...},
    "environment": {...},
    "user_requirement": {"goal": "weight_loss"},
    "num_candidates": 3,
    "diet_only": false,
    "exercise_only": false,
    "filter_safe": true,
    "min_score": 60
}
```

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

### 统一入口 (推荐)
```bash
# 运行完整集成测试
python run.py all

# 生成饮食方案
python run.py diet --goal weight_loss

# 生成运动方案
python run.py exercise --goal weight_loss

# 启动服务器
python -m core.server
```

### 独立模块测试
```python
# test_diet.py
from agents.diet import generate_diet_candidates

candidates = generate_diet_candidates(
    user_metadata={...},
    user_requirement={"goal": "weight_loss"},
    num_candidates=2
)
```

---

## 三种Agent职责

| Agent | 输入 | 输出 |
|-------|------|------|
| DietAgent | user_metadata + env + requirement | 饮食候选 (含营养素) |
| ExerciseAgent | user_metadata + env + requirement | 运动候选 (含卡路里) |
| SafeguardAgent | plan + user_metadata + env | {0-100分, is_safe, 风险因素} |

---

## 架构特点

### 1. BaseAgent + Mixin 模式
- `BaseAgent`: 提供通用 Agent 功能（LLM 调用、输入解析）
- `DietAgentMixin`: 饮食知识查询
- `ExerciseAgentMixin`: 运动知识查询

### 2. Pydantic 数据模型
所有输入输出都有严格的类型验证：
```python
class DietAgentInput(BaseModel):
    user_metadata: Dict[str, Any]
    environment: Optional[Dict[str, Any]] = None
    user_requirement: Optional[Dict[str, Any]] = None
    num_candidates: int = 3

class DietRecommendation(BaseModel):
    id: int
    meal_plan: Dict[str, List[FoodItem]]
    total_calories: int
    calories_deviation: float
    macro_nutrients: MacroNutrients
    safety_notes: List[str]
```

### 3. 健康管道编排
```python
class HealthPlanPipeline:
    def generate(self, input_data):
        # 1. 饮食方案生成
        diet_candidates = diet_agent.generate(...)

        # 2. 运动方案生成
        exer_candidates = exercise_agent.generate(...)

        # 3. 安全评估
        for plan in diet_candidates + exer_candidates:
            score = safeguard.evaluate(plan, ...)

        # 4. 排序返回
        return safe_plans_sorted_by_score
```

---

## 最近的 Bug 修复

### 1. 枚举值大小写问题
- **问题**: LLM 返回大写枚举值 (`'CARDIO'`, `'LOW'`)，但 Pydantic 期望小写
- **修复**: 添加 `_normalize_enum_values()` 方法自动转换

### 2. 关系类型显示为 "RELATION"
- **问题**: `import_kg.py` 硬编码关系类型为 `"RELATION"`
- **修复**: 使用实际关系名称（如 `"Has_Benefit"`, `"Target_Recommendation"`）
- **命令**: 重新运行 `python -m core.import_kg` 导入数据

### 3. 节点字段名大小写不匹配
- **问题**: 后端返回 `"Name"` 但前端期望 `"name"`
- **修复**: 统一使用小写 `"name"`

---

## 下一步优化方向

1. **Safeguard Agent 完善**
   - 实现完整的风险评估逻辑
   - 添加更多安全规则

2. **测试覆盖**
   - 添加单元测试
   - 添加集成测试

3. **性能优化**
   - 缓存 LLM 响应
   - 批量查询 Neo4j

4. **前端改进**
   - 支持健康方案可视化
   - 支持方案对比
