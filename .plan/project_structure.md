# 项目结构设计

## 整体架构

```
kg_agents/
├── .plan/                      # 项目规划文档
│   ├── targets.md             # 任务目标和里程碑
│   ├── project_structure.md    # 本文件
│   └── prompts.txt             # Prompt模板库
├── .doc/                       # 文档资料
│   └── neo4j.md               # Neo4j使用指南
├── kg/                         # 核心代码
│   ├── __init__.py
│   ├── server_local.py         # FastAPI服务（问答+图谱查询）
│   ├── build_kg_deepseek.py   # 知识图谱构建器（文档→三元组）
│   ├── build_neo4j_database.py # 数据导入（文件→Neo4j）
│   ├── diet_generator.py       # ✅ 已完成: 饮食候选方案生成器
│   ├── prompts/               # Prompt模板
│   │   ├── __init__.py
│   │   └── diet_kg.py         # 饮食图谱提取Prompt
│   ├── data/                   # 输入数据
│   │   ├── diet/             # 饮食知识文档
│   │   ├── exercise/         # 运动知识文档
│   │   └── health/           # 健康标准文档
│   ├── templates/             # Web UI模板
│   │   └── index.html
│   └── output_history/         # 构建历史输出
├── agents/                      # Agent模块 (待实现)
│   ├── __init__.py
│   ├── base.py                # Agent基类
│   ├── exercise_generator.py  # 运动候选方案生成器
│   └── safeguard.py          # 风险评估模块
├── pipeline/                    # 管道编排 (待实现)
│   ├── __init__.py
│   ├── health_pipeline.py    # 主流程编排
│   └── candidate_processor.py # 方案处理变换
├── parsers/                     # Parser规则 (待实现)
│   ├── __init__.py
│   ├── diet_parser.py        # 饮食方案解析
│   ├── exercise_parser.py     # 运动方案解析
│   └── response_parser.py     # 统一响应解析
├── models/                      # 数据模型
│   ├── __init__.py
│   ├── user.py               # 用户输入模型
│   ├── plan.py               # 方案模型
│   └── assessment.py          # 评估结果模型
├── config.json                 # API密钥和配置
└── requirements.txt            # Python依赖
```

## 配置说明

所有API密钥和数据库配置集中在 `config.json`：

```json
{
    "neo4j": {
        "uri": "bolt://127.0.0.1:7687",
        "username": "neo4j",
        "password": "your_password"
    },
    "deepseek": {
        "api_key": "sk-...",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
    }
}
```

**注意**: `config.json` 不应提交到版本控制（已在 `.gitignore` 中忽略）。

## 运行管道

### 阶段0: 配置

```bash
# 编辑配置文件
# 修改 config.json 中的 neo4j 密码和 deepseek api_key
```

### 阶段1: 知识图谱构建

```bash
# 1. 启动Neo4j
net start Neo4j

# 2. 导入三元组数据到Neo4j
python -m kg.build_neo4j_database

# 3. (可选) 从文档构建知识图谱
python -m kg.build_kg_deepseek
```

### 阶段2: 饮食方案生成器 (Milestone 1 ✅ 已完成)

#### 2.1 初始化食物数据库到Neo4j

```bash
# 方法1: 通过API初始化
curl -X POST http://localhost:8000/api/diet/init_db

# 方法2: 直接运行
python -c "from kg.diet_generator import init_food_database_in_kg; init_food_database_in_kg()"
```

#### 2.2 测试饮食生成器

```bash
python kg/diet_generator.py
```

#### 2.3 启动服务

```bash
# 开发模式
python -m kg.server_local

# 生产模式
uvicorn kg.server_local:app --host 0.0.0.0 --port 8000
```

### 阶段3: API接口使用

#### 饮食方案生成 API

```bash
POST /api/diet/generate
Content-Type: application/json

{
  "user_metadata": {
    "age": 35,
    "gender": "male",
    "height_cm": 175,
    "weight_kg": 70,
    "bmi": 22.9,
    "medical_conditions": ["糖尿病"],
    "dietary_restrictions": ["low_sodium"],
    "fitness_level": "intermediate"
  },
  "environment": {
    "weather": {"condition": "clear", "temperature_c": 25},
    "time_context": {"season": "summer", "time_of_day": "morning"}
  },
  "user_requirement": {
    "goal": "weight_loss"
  },
  "num_candidates": 3,
  "sampling_strategy": "balanced"  // balanced/calorie_optimal/protein_priority/variety_priority
}
```

#### 响应格式

```json
{
  "candidates": [
    {
      "id": 1,
      "meal_plan": {
        "breakfast": [{"food": "燕麦粥", "portion": "100g", "calories": 150}],
        "lunch": [{"food": "清蒸鱼", "portion": "150g", "calories": 150}],
        "dinner": [...],
        "snack": [...]
      },
      "total_calories": 1650,
      "calories_deviation": 10.0,
      "macro_nutrients": {
        "protein": 75.5,
        "carbs": 180.2,
        "fat": 45.3,
        "protein_ratio": 18.3
      },
      "safety_notes": ["目标热量: 1500kcal, 实际: 1650kcal"],
      "nutrition_analysis": {
        "protein_pct": 18.3,
        "fat_pct": 24.6,
        "carbs_pct": 57.1,
        "suggestions": []
      }
    }
  ],
  "target_calories": 1500,
  "user_conditions": ["糖尿病", "健康人群"],
  "sampling_strategy": "balanced",
  "retrieval_stats": {
    "retrieved_meal_types": ["breakfast", "lunch", "dinner", "snack"],
    "has_kg_data": true
  }
}
```

### 阶段4: Agent模块（Milestone 2+ 待实现）

```python
# 待实现: 完整管道
from pipeline.health_pipeline import HealthPlanPipeline

pipeline = HealthPlanPipeline()
result = pipeline.generate(
    user_metadata={...},
    environment={...},
    user_requirement={...}
)
```

## 模块依赖关系

```
用户输入
    ↓
┌─────────────────────────────────────────────────────────────┐
│  diet_generator.py (✅ 已完成)                              │
│  ├── Phase 1: 食物数据库 + API端点                          │
│  ├── Phase 2: NL-to-Cypher + 多约束查询构建器              │
│  └── Phase 3: 知识检索 + 餐计划采样器                       │
└─────────────────────────────────────────────────────────────┘
    ├── 查询知识图谱 → Knowledge Graph
    ├── 多约束Cypher生成 → MultiConstraintQueryBuilder
    └── 餐计划采样 → MealPlanSampler
            ↓
        最终输出: 饮食候选方案列表
```

## 数据流

```
输入: user_metadata + environment + user_requirement
    ↓
┌─────────────────────────────────────────────────────────────┐
│  diet_generator.py                                          │
│  ┌─────────────────┬─────────────────────────────────────┐ │
│  │ 知识检索模块    │ MultiConstraintQueryBuilder          │ │
│  │ retrieve_*()   │ add_disease_constraint()             │ │
│  │                 │ add_calorie_constraint()             │ │
│  │                 │ add_nutrient_constraint()             │ │
│  └─────────────────┴─────────────────────────────────────┘ │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ MealPlanSampler                                       │   │
│  │ • _calculate_weight()  加权计算                       │   │
│  │ • generate_meal_plan()  生成多候选                   │   │
│  │ • apply_nutrition_balance_rules()  营养均衡分析        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
    ↓
输出: 饮食候选方案 + 营养分析 + 安全提示
```

## Prompt Engineering覆盖

| 模块 | 功能 | 状态 |
|------|------|------|
| diet_generator | NL-to-Cypher翻译 | ✅ 已完成 |
| | 多约束查询构建 | ✅ 已完成 |
| | 知识检索增强 | ✅ 已完成 |
| exercise_generator | 待实现 | ⏳ |
| safeguard | 待实现 | ⏳ |

## Parser覆盖规则

| 功能 | 状态 |
|------|------|
| 食物多样性计算 (get_diversity_score) | ✅ |
| 营养素约束 (蛋白质/脂肪/纤维) | ✅ |
| 热量约束过滤 | ✅ |
| 餐类型分类 | ✅ |
| 营养均衡分析 | ✅ |

## 当前进度

| Milestone | 任务 | 状态 |
|-----------|------|------|
| Milestone 1 | Diet Generator框架 | ✅ 已完成 |
| - Phase 1 | 食物数据库 + API端点 | ✅ |
| - Phase 2 | NL-to-Cypher + 多约束查询 | ✅ |
| - Phase 3 | 知识检索 + 餐计划采样 | ✅ |
| Milestone 2 | Exercise Generator框架 | ⏳ 待实现 |
| Milestone 3 | Prompt调优 + 测试数据 | ⏳ 待实现 |
| Milestone 4 | Safeguard模块 | ⏳ 待实现 |
