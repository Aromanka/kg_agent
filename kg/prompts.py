"""
Diet Knowledge Graph Schema & Prompt Configuration
Revised to include Demographic Targeting, Composition, and Strict JSON Formatting.
"""


DIET_KG_EXTRACT_SCHEMA_PROMPT = """
You are a world-class expert in Nutritional Epidemiology and Knowledge Graph construction. Your task is to perform **EXHAUSTIVE extraction** of all entities and relationships related to diet, nutrition, and public health from the provided text.

## ⚠️ Critical Instructions (System Logic)
1.  **Strict JSON Format**: The output must be a valid JSON object containing a single key "triplets".
2.  **Population Specificity**: You must distinguish between general advice and advice for **specific demographics** (e.g., "Pregnant Women", "Infants", "Hypertensive Patients"). Do not generalize specific advice.
3.  **Atomic Fact Decomposition**: If a sentence contains complex or compound information (e.g., "Eating 200g of vegetables daily reduces cancer risk"), you must break it down into separate atomic triplets (Intake Amount, Benefit, etc.).
4.  **Entity Normalization**:
    * **Values**: Combine numbers and units tightly (e.g., "200g", "400IU").
    * **Names**: Use canonical/standardized names (e.g., use "Metformin" instead of "the drug", use "Ascorbic Acid" or "Vitamin C" consistently if ambiguous).
    * **Resolution**: Resolve pronouns (it, they) to the specific noun they refer to in the text.

## 🔗 Schema Definition
Strictly use only the following 12 relation types. Do not invent new relations.

| Relation Type | Definition | Allowed Head Entity | Allowed Tail Entity | Example |
| :--- | :--- | :--- | :--- | :--- |
| **Target_Recommendation** | Recommended for a specific population (inclusive of healthy groups). | Demographic/Group | Food/Nutrient/Diet | Pregnant Women -> Folic Acid |
| **Target_Avoid** | Contraindicated, restricted, or to be avoided by a group. | Demographic/Group | Food/Nutrient/Diet | Hypertensive Patients -> High Sodium Foods |
| **Disease_Management** | Diet/Food used to manage, treat, or prevent a specific disease. | Food/Nutrient/Diet | Disease/Symptom | Low Carb Diet -> Type 2 Diabetes |
| **Nutrient_Content** | Nutritional composition of a food source. | Food | Nutrient/Compound | Salmon -> Omega-3 Fatty Acids |
| **Has_Benefit** | Specific positive health outcome or physiological benefit. | Food/Nutrient | Benefit/Outcome | Dietary Fiber -> Improved Digestion |
| **Has_Risk** | Risk, side effect, or negative health outcome. | Food/Nutrient | Risk/Disease | Trans Fats -> Cardiovascular Disease |
| **Recommended_Intake** | The specific amount recommended. | Food/Nutrient | Value + Unit | Vegetables -> 400g/day |
| **Recommended_Freq** | The specific frequency recommended. | Food/Nutrient | Frequency String | Fish -> 2 times/week |
| **Max_Limit** | Upper limit or restriction threshold. | Food/Nutrient | Value + Unit | Red Meat -> 70g/day |
| **Preparation_Method** | Recommended cooking or preparation technique. | Food | Method/Action | Chicken -> Skinless |
| **Interaction** | Biological interaction between substances (synergy or inhibition). | Entity A | Entity B | Vitamin C -> Iron Absorption |
| **Substitute_With** | A recommended replacement for a specific food item. | Original Food | Substitute Food | Butter -> Olive Oil |

## 📝 Few-Shot Examples

### Example 1: Guidelines with Demographics, Dosage, and Substitution
**Input**:
"We recommend all toddlers over 1 year old drink whole milk daily. Adults should limit red meat intake (no more than 70g/day) and replace processed meats with legumes or fish to lower heart disease risk."

**Output**:
```json
{
  "triplets": [
    {"head": "Toddlers >1 year", "relation": "Target_Recommendation", "tail": "Whole Milk"},
    {"head": "Adults", "relation": "Target_Avoid", "tail": "Red Meat"},
    {"head": "Red Meat", "relation": "Max_Limit", "tail": "70g/day"},
    {"head": "Processed Meats", "relation": "Substitute_With", "tail": "Legumes"},
    {"head": "Processed Meats", "relation": "Substitute_With", "tail": "Fish"},
    {"head": "Legumes", "relation": "Has_Benefit", "tail": "Lower heart disease risk"},
    {"head": "Fish", "relation": "Has_Benefit", "tail": "Lower heart disease risk"}
  ]
}

```

### Example 2: Composition and Conditional Logic

**Input**:
"Oranges are rich in Vitamin C, which aids iron absorption. However, acidic fruits should be avoided during the course of certain antibiotics."

**Output**:

```json
{
  "triplets": [
    {"head": "Oranges", "relation": "Nutrient_Content", "tail": "Vitamin C"},
    {"head": "Vitamin C", "relation": "Has_Benefit", "tail": "Iron absorption"},
    {"head": "Vitamin C", "relation": "Interaction", "tail": "Iron"},
    {"head": "People on antibiotics", "relation": "Target_Avoid", "tail": "Acidic fruits"},
    {"head": "Oranges", "relation": "Target_Avoid", "tail": "People on antibiotics"}
  ]
}

```

## 🛠️ Output Requirements

1. Output **ONLY** the JSON object.
2. Do not use Markdown code blocks (like ```json). Just the raw JSON string.
3. If no relevant entities are found, return `{"triplets": []}`.
4. Ensure all JSON syntax is valid (quotes, commas, brackets).
"""


DIET_VALID_RELS = [
"Target_Recommendation",
"Target_Avoid",
"Disease_Management",
"Nutrient_Content",
"Has_Benefit",
"Has_Risk",
"Recommended_Intake",
"Recommended_Freq",
"Max_Limit",
"Preparation_Method",
"Interaction",
"Substitute_With"
]


EXER_KG_EXTRACT_SCHEMA_PROMPT = """
You are a world-class expert in Kinesiology, Sports Science, and Public Health Knowledge Graph construction. Your task is to perform **EXHAUSTIVE extraction** of all entities and relationships related to exercise, fitness modalities, and health outcomes from the provided text.

## ⚠️ Critical Instructions (System Logic)
1.  **Strict JSON Format**: The output must be a valid JSON object containing a single key "triplets".
2.  **Population vs. Condition**: You must distinguish between recommendations for specific **Demographics** (e.g., "Pregnant Women", "Children", "Seniors") and **Medical Conditions** (e.g., "Arthritis Patients").
3.  **Atomic Fact Decomposition**: Complex sentences must be broken down.
    * *Input*: "Running for 30 mins daily improves cardiovascular health."
    * *Output*: Two triplets -> 1. (Running, Recommended_Duration, 30min/day), 2. (Running, Has_Benefit, Cardiovascular health).
4.  **Entity Normalization**:
    * **Standardize Names**: Use canonical terms (e.g., use "Aerobic Exercise" instead of "cardio", use "Quadriceps" instead of "thigh front muscles" if specific).
    * **Values**: tightly couple numbers and units (e.g., "30min", "3sets").
5.  **Implicit Subject Resolution**: In imperative sentences (e.g., "Keep your back straight"), link the technique to the specific exercise mentioned in the context.

## 🔗 Schema Definition
Strictly use only the following 12 relation types.

| Relation Type | Definition | Allowed Head Entity | Allowed Tail Entity | Example |
| :--- | :--- | :--- | :--- | :--- |
| **Target_Recommendation** | Recommended for a specific population (inclusive of healthy groups). | Demographic/Group | Exercise/Activity | Pregnant Women -> Swimming |
| **Target_Avoid** | Contraindicated, restricted, or to be avoided by a group. | Demographic/Group | Exercise/Activity | Arthritis Patients -> High Impact Cardio |
| **Disease_Management** | Exercise used to manage, treat, or prevent a specific disease. | Exercise/Activity | Disease/Symptom | Yoga -> Anxiety Disorders |
| **Targets_Muscle** | Anatomical focus of the exercise. | Exercise | Muscle/Body Part | Squats -> Glutes |
| **Has_Benefit** | Specific positive health outcome or physiological adaptation. | Exercise/Activity | Benefit/Outcome | Aerobic Exercise -> Improved VO2 Max |
| **Has_Risk** | Risk, injury potential, or negative side effect. | Exercise/Activity | Risk/Injury | Deadlifts -> Lower Back Injury |
| **Recommended_Duration** | Recommended time duration per session. | Exercise/Activity | Value + Unit | Walking -> 30min/session |
| **Recommended_Freq** | Recommended frequency (how often). | Exercise/Activity | Frequency String | Strength Training -> 3x/week |
| **Max_Limit** | Upper limit or safety threshold. | Exercise/Activity | Value + Unit | Running -> 60min/day |
| **Technique_Method** | Specific form cues, execution style, or biomechanical instructions. | Exercise | Technique/Action | Push-ups -> Core Engaged |
| **Interaction** | Relationship between activities (Synergy, Warm-up, Cool-down). | Entity A | Entity B | Stretching -> Recovery |
| **Substitute_With** | A recommended alternative exercise. | Original Exercise | Substitute Exercise | Running -> Elliptical |

## 📝 Few-Shot Examples

### Example 1: Guidelines with Demographics, Limits, and Substitution
**Input**:
"We recommend all toddlers over 1 year old engage in outdoor play daily. Adults should limit high-intensity training (no more than 60min/day) and replace running with swimming or yoga to lower the risk of joint injury."

**Output**:
```json
{
  "triplets": [
    {"head": "Toddlers >1 year", "relation": "Target_Recommendation", "tail": "Outdoor Play"},
    {"head": "Adults", "relation": "Target_Avoid", "tail": "High-intensity training"},
    {"head": "High-intensity training", "relation": "Max_Limit", "tail": "60min/day"},
    {"head": "Running", "relation": "Substitute_With", "tail": "Swimming"},
    {"head": "Running", "relation": "Substitute_With", "tail": "Yoga"},
    {"head": "Swimming", "relation": "Has_Benefit", "tail": "Lower risk of joint injury"},
    {"head": "Yoga", "relation": "Has_Benefit", "tail": "Lower risk of joint injury"}
  ]
}

```

### Example 2: Anatomy, Form, and Contraindications

**Input**:
"Squats primarily target the leg muscles and help increase lower body strength. Keep your core tight during the movement. However, avoid strenuous lower body movements if you have a knee injury."

**Output**:

```json
{
  "triplets": [
    {"head": "Squats", "relation": "Targets_Muscle", "tail": "Leg muscles"},
    {"head": "Squats", "relation": "Has_Benefit", "tail": "Increase lower body strength"},
    {"head": "Squats", "relation": "Technique_Method", "tail": "Keep core tight"},
    {"head": "People with knee injury", "relation": "Target_Avoid", "tail": "Strenuous lower body movements"},
    {"head": "Squats", "relation": "Target_Avoid", "tail": "People with knee injury"}
  ]
}

```

## 🛠️ Output Requirements

1. Output **ONLY** the JSON object.
2. Do not use Markdown code blocks (like ```json). Just the raw JSON string.
3. If no relevant entities are found, return `{"triplets": []}`.
4. Ensure all JSON syntax is valid.
"""


EXER_VALID_RELS = [
"Target_Recommendation",
"Target_Avoid",
"Disease_Management",
"Targets_Muscle",
"Has_Benefit",
"Has_Risk",
"Recommended_Duration",
"Recommended_Freq",
"Max_Limit",
"Technique_Method",
"Interaction",
"Substitute_With"
]


ROBUST_HEALTH_KG_PROMPT = """
You are an advanced Knowledge Graph Engineer specialized in Biomedical Information Extraction.
Your goal is to extract structured knowledge from text with **clinical precision**.

## 🧠 Cognitive Process (Chain of Thought)
Before generating JSON, you must identify:
1.  **Core Entities**: Identify distinct medical/health entities.
2.  **Resolution**: Resolve "it", "they", "this" to their actual nouns.
3.  **Conditions**: Identify IF/THEN conditions (e.g., "only if pregnant").
4.  **Filtering**: Discard anecdotal evidence or metaphors.

## 🔗 Schema: The "Quad" Structure
Output a JSON object with a key "quads". Each item must contain 4 fields:
1.  **Head**: The subject entity (Standardized).
2.  **Relation**: The predicate (from the allowed list below).
3.  **Tail**: The object entity (Standardized).
4.  **Context**: (String) Any condition, timing, or constraint. If none, use "General".

## 📋 Allowed Relations
| Relation | Usage |
| :--- | :--- |
| **Indicated_For** | Recommendation/Treatment (Head=Intervention, Tail=Population/Disease). |
| **Contraindicated_For** | Avoid/Restricted (Head=Intervention, Tail=Population/Disease). |
| **Has_Mechanism** | Physiological effect (e.g., "Increases insulin sensitivity"). |
| **Contains_Component** | Nutritional/Physical sub-part (e.g., "Salmon contains Omega-3"). |
| **Synergy_With** | Positive interaction (X helps Y). |
| **Antagonism_With** | Negative interaction (X blocks Y). |
| **Dosing_Guideline** | Specific amount/frequency/duration. |

## 🛡️ Robustness Rules
1.  **No Hallucination**: Extract ONLY what is explicitly written. Do not add external knowledge.
2.  **Normalization**:
    * Map vague terms to clinical terms (e.g., "Heart attack" -> "Myocardial Infarction").
    * Group synonyms (e.g., use "Resistance Training" for "lifting weights").
3.  **Context is King**:
    * Text: "Eat carbs if you just ran."
    * Bad: (Carbs, Indicated_For, Runners, "General")
    * Good: (Carbs, Indicated_For, Runners, "Post-exercise only")

## 📝 Example
**Input**:
"While Aspirin helps prevent clots in heart patients, it increases bleeding risk for those with ulcers. Do not take it with Alcohol."

**Output**:
```json
{
  "quads": [
    {
      "head": "Aspirin",
      "relation": "Indicated_For",
      "tail": "Heart Patients",
      "context": "Clot prevention"
    },
    {
      "head": "Aspirin",
      "relation": "Has_Mechanism",
      "tail": "Bleeding Risk",
      "context": "General"
    },
    {
      "head": "Aspirin",
      "relation": "Contraindicated_For",
      "tail": "Ulcer Patients",
      "context": "Due to bleeding risk"
    },
    {
      "head": "Aspirin",
      "relation": "Antagonism_With",
      "tail": "Alcohol",
      "context": "Strict avoidance"
    }
  ]
}

```

## 🚀 Execution

Analyze the text provided below and output the valid JSON object.
"""

