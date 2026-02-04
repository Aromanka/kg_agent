# 任务目标：
基于 LLM+知识图谱 的agent项目。
需要有**diet_candidate_generator**(饮食候选方案生成器), **exer_candidate_generator**(运动候选方案生成器),**safeguard**(风险评估模块)三个基于{知识图谱, LLM, prompt_engineering, parser_rules}的模块。
其中**diet_candidate_generator**, **exer_candidate_generator**用于在饮食/运动知识图谱指导下生成方案采样。随后方案会经过一系列处理和变换，再由**safeguard**衡量后输出。

方案生成支持：
1. 根据用户metadata（生理指标）、当前的环境变量（天气/日期/时间）生成多个候选方案
2. 根据用户metadata（生理指标）、当前的环境变量（天气/日期/时间）与用户的需求生成多个候选方案

风险评估模块支持：
1. 对于给出的用户metadata（生理指标）、当前的环境变量（天气/日期/时间）和具体方案，输出一个{0-100分的标量/True or False的判断}，判定方案是否安全。

# 任务规划:

### milestone设置
1. milestone 1: 实现单个diet candidate generator的项目框架
2. milestone 2: 基于milestone 1的单个框架，扩展出exer candidate generator的框架
   milestone 2.5: 准备一定的测试数据
3. milestone 3: 基于框架和测试数据，调试出两个generator最优秀的prompt和parser
4. milestone 4: 基于两个generator的实现，扩展出safeguard并完成调试
5. milestone n[future]: 扩展到完整数据集上进行测试。

### **数据需求**
1. **知识图谱数据**
   - 饮食知识图谱：食物营养成分表（至少1000种食物）、食物搭配禁忌、疾病饮食建议
   - 运动知识图谱：运动类型库、运动消耗卡路里数据、运动风险系数
   - 健康标准库：BMI标准、血压/血糖标准、各疾病人群安全阈值

2. **示例数据**
   - 用户metadata示例集
   - 安全/不安全方案标注数据：方案+安全评分

### **输入格式标准**
```json
{
  "user_metadata": {
    "age": 35,
    "gender": "male",
    "height_cm": 175,
    "weight_kg": 70,
    "bmi": 22.9,
    "medical_conditions": ["hypertension", "diabetes"],
    "dietary_restrictions": ["low_sodium", "low_sugar"],
    "fitness_level": "intermediate"
  },
  "environment": {
    "weather": {
      "condition": "rainy",
      "temperature_c": 18,
      "humidity_percent": 85,
      "aqi": 45
    },
    "time_context": {
      "date": "2024-03-15",
      "time_of_day": "morning",
      "season": "spring"
    }
  },
  "user_requirement": {  // 可选
    "goal": "weight_loss",
    "intensity": "moderate",
    "preferences": ["prefer_indoor", "vegetarian"]
  }
}
```

### **2.1 diet_candidate_generator**
#### **Prompt Engineering设计**
```python
DIET_GENERATION_PROMPT = {
  "system_role": "你是一个专业的营养师，基于知识图谱数据生成个性化的饮食方案。",
  "components": [
    {
      "name": "knowledge_retrieval",
      "prompt": "基于用户疾病{medical_conditions}，从知识图谱中检索必须遵循的饮食原则和禁忌食物。"
    },
    {
      "name": "meal_generation",
      "prompt": "生成{meal_count}个候选方案，每个方案包含：早餐、午餐、晚餐、加餐，具体到食物种类和分量(g/ml)。考虑季节{season}和天气{weather_condition}的影响。"
    },
    {
      "name": "nutrition_calculation",
      "prompt": "计算每个方案的总热量、蛋白质、碳水化合物、脂肪含量，确保符合用户{goal}目标。"
    }
  ],
  "output_format": "返回JSON数组，每个方案包含meal_plan、total_calories、macro_nutrients、safety_notes字段"
}
```

#### **Parser Rules覆盖类型**
1. **结构化提取**
   ```python
   class DietPlanParser:
     def parse_llm_output(self, text):
         # 规则1：提取JSON格式的方案数据
         # 规则2：验证营养成分计算的合理性
         # 规则3：检查食物禁忌冲突（调用知识图谱验证）
         # 规则4：统一计量单位转换
   ```

### **2.2 exer_candidate_generator**
#### **Prompt Engineering设计**
```python
EXER_GENERATION_PROMPT = {
  "system_role": "你是一个专业的健身教练，考虑用户健康状况和环境因素制定运动计划。",
  "constraints": [
    "必须考虑用户的{fitness_level}水平",
    "在{weather_condition}天气下推荐合适的运动类型",
    "避免与{medical_conditions}冲突的运动",
    "逐步增加强度的progressive_overload原则"
  ],
  "generation_logic": "从{intensity_low}到{intensity_high}生成3个强度等级的运动方案",
  "safety_checkpoints": ["心率区间控制", "关节负荷评估", "环境适应性"]
}
```

#### **Parser Rules覆盖类型**
1. **运动方案解析**
   ```python
   patterns = {
     'duration': r'(\d+)\s*(分钟|min|小时|hr)',
     'intensity': r'(低|中|高|low|medium|high)强度',
     'type': r'(有氧|力量|柔韧性|平衡性)训练'
   }
   ```

### **safeguard模块实现方案**
#### **双层评估架构**
1. **规则引擎（确定性评估）**
   ```python
   class RuleBasedSafetyChecker:
     def check(self, plan, user_metadata):
         # 规则1：热量极端值检查（<800或>4000卡路里）
         # 规则2：疾病禁忌匹配（知识图谱查询）
         # 规则3：环境风险（高温下高强度运动）
         # 规则4：营养均衡性检查
   ```

2. **LLM语义评估（概率性评估）**
   ```python
   SAFETY_PROMPT = """
   作为医疗安全专家，评估以下方案的安全性：
   用户状况：{medical_summary}
   方案详情：{plan_details}
   
   请从以下维度评分（0-100）：
   1. 疾病兼容性（权重40%）
   2. 强度适宜性（权重30%）
   3. 环境适应性（权重20%）
   4. 可持续性（权重10%）
   
   输出格式：{"total_score": 85, "risk_factors": [...], "recommendations": [...]}
   """
   ```

#### **输出格式**
```json
{
  "safety_assessment": {
    "score": 85,
    "is_safe": true,
    "risk_level": "low",
    "risk_factors": [
      {"factor": "high_intensity", "severity": "medium"},
      {"factor": "weather_risk", "severity": "low"}
    ],
    "confidence": 0.92,
    "threshold_used": 70
  }
}
```

### **4.1 管道集成设计**
```python
class HealthPlanPipeline:
    def generate_candidates(self, input_data):
        # 步骤1：知识图谱查询
        kg_context = self.query_knowledge_graph(input_data)
        
        # 步骤2：候选方案生成
        diet_candidates = diet_generator.generate(
            user_data=input_data,
            kg_context=kg_context,
            count=5  # 生成5个候选
        )
        
        # 步骤3：安全过滤
        safe_diets = []
        for plan in diet_candidates:
            score = safeguard.evaluate(plan, input_data)
            if score['is_safe']:
                safe_diets.append({
                    'plan': plan,
                    'safety_score': score['score']
                })
        
        # 步骤4：排序返回（安全性>个性化匹配度）
        return sorted(safe_diets, key=lambda x: x['safety_score'], reverse=True)[:3]
```

### **4.2 Prompt Engineering覆盖任务类型**
| 任务类型 | 使用场景 | 示例模板数 |
|---------|---------|-----------|
| **检索增强生成** | 知识图谱查询+方案生成 | —— |
| **约束条件注入** | 疾病限制、环境限制 | 多约束模板 |
| **多方案生成** | 不同强度/偏好方案 | 2套变体策略 |
| **安全评估** | 多维风险评估 | 多维度评分模板 |
| **解释生成** | 方案理由说明 | 1套解释模板 |


##### Milestone 1: Detailed Task:
为了实现 饮食/运动方案生成器 和 风险评估模块，你需要将目前的“问答模式”升级为“规划模式”。目前的 search_kg 只是简单的关键词匹配，无法完成复杂的“方案采样”和“约束过滤”。

1. Diet Candidate Generator (饮食候选方案生成器)
现状缺失： 当前代码仅能回答“什么是二甲双胍”或“二甲双胍治什么”，无法主动生成“早餐吃什么”的方案列表。

需要增加的功能：

结构化查询构建 (Cypher Generation)：需要利用 LLM 将用户的自然语言需求（如“适合糖尿病的低卡食物”）转化为特定的 Cypher 查询语句，而不是简单的全文索引搜索。

目标查询示例：MATCH (f:Food)-[:Suitable_For]->(d:Disease {name: 'Diabetes'}) RETURN f.name, f.calories

采样策略 (Sampling Logic)：代码中需要增加逻辑，从图谱返回的几十种食物中，根据营养学规则（Parser Rules）随机或加权采样，组合成早餐、午餐、晚餐的候选池。

##### Milestone 2: Detailed Task:
2. Exer Candidate Generator (运动候选方案生成器)
现状缺失： 同上，当前代码没有处理运动强度、时长与用户体能匹配的逻辑。

需要增加的功能：

属性过滤 (Attribute Filtering)：在检索图谱时，需要利用 parser_rules 对图谱中的属性进行硬过滤。

逻辑示例：如果用户是“膝关节损伤”，代码必须解析出图谱中 Constraint 属性，过滤掉“跑步”或“跳绳”等高冲击运动。

参数化生成：利用 Prompt Engineering 指导 LLM 读取图谱中的 Frequency（频率）和 Duration（时长）关系，生成具体的运动处方（如：慢跑，30分钟，每周3次）。

##### Milestone 4: Detailed Task:
3. Safeguard (风险评估模块)
现状缺失： 当前的 validate_and_correct 仅用于核查“回答是否符合事实”，它不具备“预测潜在风险”的能力。它能发现“药物剂量写错了”，但无法发现“这个运动方案可能导致该用户低血糖”。

需要增加的功能：

禁忌检索 (Contraindication Retrieval)：

需要在生成方案后，反向查询图谱中的 Bindication_Disease (禁忌症) 或 Interfere_Test_items (干扰因素) 关系（参考之前提供的 Schema）。

逻辑推理链 (Reasoning Chain)：

Input: 用户画像 (e.g., "高血压") + 生成的方案 (e.g., "举重")。

KG Query: 查询“举重”与“高血压”之间是否存在负面边。

LLM Decision: 如果图谱中存在 (Weightlifting)-[:Risk_For]->(Hypertension)，Safeguard 模块必须拦截并修改方案。