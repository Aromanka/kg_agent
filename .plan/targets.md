# 任务目标：
基于 LLM+知识图谱 的agent项目。
需要有**diet_candidate_generator**(饮食候选方案生成器), **exer_candidate_generator**(运动候选方案生成器),**safeguard**(风险评估模块)三个基于{知识图谱, LLM, prompt_engineering, parser_rules}的模块。
其中**diet_candidate_generator**, **exer_candidate_generator**用于在饮食/运动知识图谱指导下生成方案采样。随后方案会经过一系列处理和变换，再由**safeguard**衡量后输出。

方案生成支持：
1. 根据用户metadata（生理指标）、当前的环境变量（天气/日期/时间）生成多个候选方案
2. 根据用户metadata（生理指标）、当前的环境变量（天气/日期/时间）与用户的需求生成多个候选方案

风险评估模块支持：
1. 对于给出的用户metadata（生理指标）、当前的环境变量（天气/日期/时间）和具体方案，输出一个{0-100分的标量/True or False的判断}，判定方案是否安全。

---

# 当前进度：Milestone 1 已完成 ✅

## 已完成功能

### Diet Candidate Generator (饮食候选方案生成器)
- ✅ **LLM-based饮食生成**: 移除硬编码FOOD_DATABASE，改用LLM动态生成
- ✅ **Pydantic JSON Schema**: 定义了FoodItem, MealPlanItem, DietRecommendation等结构化输出模型
- ✅ **Harris-Benedict BMR计算**: 自动计算目标热量
- ✅ **疾病约束处理**: 糖尿病/高血压/高血脂等饮食限制
- ✅ **环境适应**: 根据季节/天气调整饮食建议
- ✅ **多候选生成**: 支持生成多个饮食方案候选

### 输入输出格式
```json
// 输入
{
  "user_metadata": {
    "age": 35, "gender": "male", "height_cm": 175, "weight_kg": 70,
    "medical_conditions": ["diabetes"], "fitness_level": "intermediate"
  },
  "environment": {"time_context": {"season": "summer"}},
  "user_requirement": {"goal": "weight_loss"}
}

// 输出
{
  "candidates": [...],
  "target_calories": 1800,
  "generation_notes": "基于用户1个健康状况生成..."
}
```

---

# 待实现功能

## Milestone 2: Exercise Candidate Generator (待实现)

### 需求
- 运动类型库（跑步/游泳/力量训练等）
- 运动消耗卡路里数据
- 运动风险系数
- 强度/时长与用户体能匹配

### 实现目标
```
输入: user_metadata + environment + user_requirement
  ↓
运动知识图谱查询
  ↓
LLM生成运动方案
  ↓
输出: 运动候选方案列表（包含类型/时长/频率/强度）
```

## Milestone 3: Safeguard 风险评估模块 (待实现)

### 需求
- 禁忌检索：反向查询KG中的禁忌关系
- 规则引擎：热量极端值/疾病禁忌/环境风险检查
- LLM语义评估：多维度安全性评分

### 输出格式
```json
{
  "safety_assessment": {
    "score": 85,
    "is_safe": true,
    "risk_level": "low",
    "risk_factors": [...],
    "recommendations": [...]
  }
}
```

## Milestone 4: 管道集成 (待实现)

### 需求
```python
class HealthPlanPipeline:
    def generate(self, input_data):
        # 1. 饮食方案生成
        diet_candidates = diet_generator.generate(...)

        # 2. 运动方案生成
        exer_candidates = exer_generator.generate(...)

        # 3. 安全评估
        for plan in diet_candidates + exer_candidates:
            score = safeguard.evaluate(plan, input_data)

        # 4. 排序返回
        return safe_plans_sorted_by_score
```

---

# 数据需求

## 知识图谱数据
- 饮食知识图谱：食物营养成分表、食物搭配禁忌、疾病饮食建议
- 运动知识图谱：运动类型库、运动消耗卡路里数据、运动风险系数

## 测试数据
- 用户metadata示例集
- 安全/不安全方案标注数据
