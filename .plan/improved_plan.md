基于您提供的代码文件，我对该项目的 Prompt 设计和生成逻辑进行了深入分析。

**核心结论**：
当前设计确实存在**严重的“喧宾夺主”问题**。代码逻辑中包含大量的**随机化约束（Randomized Constraints）和预设策略**，这些硬性约束在 Prompt 构建过程中往往会覆盖或干扰用户的 `user_query`。

以下是具体的**不合理处分析**及**对应的改进方案**。

---

### 一、 核心逻辑缺陷：随机化约束干扰 User Query

在 `generator.py` 层面的代码逻辑中，为了增加生成的多样性，强行注入了随机的“主项运动”或“菜系/策略”。当用户有明确意图（User Query）时，这些随机注入会导致冲突。

#### 1. 运动生成 (`agents/exercise/generator.py`)

* **不合理处**：
在 `generate` 函数中（约 248-260 行），代码逻辑如下：
```python
# 2. Randomly select primary exercises
primary_cardio = random.choice(CARDIO_ACTIVITIES)
primary_strength = random.choice(STRENGTH_MOVEMENTS)
# ...
# 7. Build constraint prompt
constraint_prompt = build_exercise_constraint_prompt(
    primary_cardio=primary_cardio,
    primary_strength=primary_strength,
    # ...
)

```


**后果**：如果用户输入 query 是 "I want to do back muscles exercise"（练背），但随机逻辑选中的 `primary_strength` 是 "Squats"（深蹲），Prompt 会强制要求 LLM 包含深蹲。这会导致 LLM 困惑或生成不符合用户需求的计划。
* **改进方案**：
当检测到 `user_preference`（即 user_query）存在时，**必须禁用或降级**这些随机强制约束。
**代码修改建议 (`agents/exercise/generator.py`)：**
```python
# 修改 generate 方法中的循环部分
for i in range(num_candidates):
    # ... (省略 meal_timing 逻辑)

    # 【改进】: 如果用户有明确偏好，不要随机指定核心动作，让 LLM 根据偏好决定
    if user_preference:
        primary_cardio = None
        primary_strength = None
        flexibility = None # 或者保留轻微的随机性，但权重要低
        equipment = None
        excluded = [] 
    else:
        # 只有当用户没说话时，才使用随机注入来保证多样性
        primary_cardio = random.choice(CARDIO_ACTIVITIES)
        primary_strength = random.choice(STRENGTH_MOVEMENTS)
        flexibility = random.choice(FLEXIBILITY_POSES)
        # ... (后续随机逻辑)

```



#### 2. 饮食生成 (`agents/diet/generator.py`)

* **不合理处**：
在 `generate` 函数中（约 198-204 行）：
```python
# [改进] 随机选择策略，尽量不重复
strategy = random.choice(remaining_strategies)
# [改进] 随机选择菜系/风格
cuisine = random.choice(available_cuisines)

```


**后果**：用户想要 "Tuna sandwich"（金枪鱼三明治），如果随机到了 `cuisine="Asian"`（亚洲菜）或 `strategy="low_carb"`（低碳水），LLM 可能会被迫把面包去掉，或者做成“金枪鱼刺身”，这完全违背了用户的“三明治”需求。
* **改进方案**：
同样，当 `user_preference` 存在时，将 `cuisine` 和 `strategy` 设置为由 User Query 驱动，或者设置为 "Adaptive"。
**代码修改建议 (`agents/diet/generator.py`)：**
```python
for mt in meal_types:
    # ...

    # 【改进逻辑】
    if user_preference:
        strategy = "User-Directed" # 告诉 Prompt 这是一个用户主导的任务
        cuisine = "As Requested"   # 或是让 LLM 自动从 query 推断
    else:
        strategy = random.choice(remaining_strategies)
        cuisine = random.choice(available_cuisines)

    # ...

```



---

### 二、 Prompt 设计缺陷：优先级模糊

当前的 Prompt 结构将 User Preference 放在了最后，且 System Prompt 没有明确权衡“用户需求”与“专业规则/知识图谱”冲突时的优先级。

#### 1. System Prompt 调整

* **不合理处**：`EXERCISE_GENERATION_SYSTEM_PROMPT` 和 `DIET_GENERATION_SYSTEM_PROMPT` 花了大量篇幅定义格式、单位和安全规则，但没有提到“Agent 必须优先满足用户意图”。
* **改进方案**：在 System Prompt 开头加入**最高指令（Prime Directive）**。
**Exercise System Prompt 改进建议：**
```python
EXERCISE_GENERATION_SYSTEM_PROMPT = """You are a professional exercise prescription AI. 

## PRIME DIRECTIVE
1. **PRIORITIZE USER INTENT**: If the user provides a specific goal, body part, or exercise preference (e.g., "back muscles", "yoga"), you MUST build the plan around that request.
2. **SAFETY**: Apply safety rules strictly, but try to accommodate the user's request safely (e.g., if a user wants HIIT but has knee pain, switch to Low-Impact HIIT).
3. **KG & CONTEXT**: Use Knowledge Graph data to enhance the plan, but do not let general data override user-specific requests.

## Guidelines
... (保留原有内容)
"""

```



#### 2. User Prompt 结构调整

* **不合理处**：在 `_build_exercise_prompt` 和 `_build_diet_prompt` 中，User Preference 被追加在 Context 之后，容易被前面的长文本（KG Context、UserProfile、Requirements）稀释。
* **改进方案**：采用 **"Instruction - Context - Constraint"** 的结构，将 User Query 提升为 **Target Task** 的核心部分。
**Exercise Prompt 构建逻辑修改 (`agents/exercise/generator.py`)：**
```python
def _build_exercise_prompt(self, ... user_preference=None):
    # ... (获取基础信息)

    prompt = f"""## TARGET TASK
Generate an exercise plan for the following user.
"""

    # 【改进】：将 User Query 放在最显眼的位置，作为核心指令
    if user_preference:
        prompt += f"""
### USER REQUEST (HIGHEST PRIORITY)
The user strictly explicitly wants: "{user_preference}"
Ensure the generated plan focuses PRIMARILY on this request.
"""

    prompt += f"""
## User Profile
...

## Requirements
...

## Knowledge Graph Context (Reference Only)
{kg_context}

## Task Constraints
...
"""
    return prompt

```



---

### 三、 知识图谱 (KG) 的利用方式

* **不合理处**：目前代码直接将检索到的 KG 三元组（Triplets）堆砌在 `## Knowledge Graph Context` 下。如果 KG 中包含通用的、与当前用户意图无关的信息（例如用户要练背，KG 检索出了“跑步对心脏好”），可能会导致 LLM 跑题。
* **改进方案**：
在 `kg/prompts.py` 或检索逻辑中，应当对检索结果进行**相关性过滤**，或者在 Prompt 中明确 KG 的作用是“补充建议”而非“强制规则”。
**Prompt 中的措辞改进**：
不要只写 `## Knowledge Graph Context`，改为：
```text
## Knowledge Graph Insights (Use these to optimize safety and effectiveness, but do not deviate from the USER REQUEST)
...

```
---

### 四、 总结：具体的执行计划

为了pipeline达到最佳效果，请按以下步骤修改：

1. **修改 `agents/exercise/generator.py**`:
* 在 `generate` 循环中，增加 `if user_preference: ... else: ...` 逻辑，**禁用随机的 `primary_strength` / `primary_cardio` 强制约束**。
* 修改 `_build_exercise_prompt`，将 `User Preference` 移动到 Prompt 的顶部，标记为 **HIGHEST PRIORITY**。


2. **修改 `agents/diet/generator.py**`:
* 在 `generate` 循环中，若存在 `user_preference`，将 `strategy` 和 `cuisine` 设为 `None` 或 "User Defined"，**禁用随机策略**。
* 同样将 `User Preference` 提到 Prompt 顶部。


3. **修改 `agents/exercise/generator.py` 中的 System Prompt**:
* 增加 `## PRIME DIRECTIVE` 章节，明确用户意图 > 预设规则。

