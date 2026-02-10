Based on the code analysis of `agents/safeguard/assessor.py`, here is the breakdown of the current evaluation metrics and the improvement plan.

### 1. Current Assessor Evaluation Metrics

The `SafeguardAgent` currently evaluates safety using a hybrid approach combining four distinct layers. The final safety score is currently calculated **before** the LLM assessment is fully integrated, meaning the current scoring relies heavily on the first three rule-based layers.

1. **Rule-Based Logic (Deterministic):**
* **Diet:** Checks calorie limits (min 1200, max 4000), macro ratios (protein > 10%, fat < 40%), and single meal caps (1500 kcal).
* **Exercise:** Checks daily duration caps based on fitness level (e.g., Beginners < 30 mins), rest day requirements (max 7 sessions/week), and HIIT frequency limits (max 3/week).


2. **Condition-Specific Restrictions (Deterministic):**
* Matches user medical conditions (e.g., Diabetes, Hypertension) against a hardcoded list of forbidden keywords in `CONDITION_RESTRICTIONS` (e.g., "sugar", "sprint", "isometric").


3. **Environmental Safety (Deterministic):**
* Checks weather conditions (Temperature > 35°C or < 5°C, Rain/Ice) against the plan type to flag environmental risks.


4. **LLM Semantic Assessment (Probabilistic):**
* Uses an LLM with Knowledge Graph context to find semantic risks (e.g., "hidden contraindications", "nutrient deficiencies") that keyword matching might miss.
* *Critique:* Currently, the code calculates the `base_score` and `severity_penalty` **before** merging the LLM results. This means the LLM's findings currently generate text warnings but **do not impact the numerical safety score**.



### 2. Improvement Plan

To achieve your goal of relying primarily on the LLM judge by default, we need to:

1. Introduce a global toggle `ENABLE_RULE_BASED_CHECKS`.
2. Refactor the `assess` method to skip deterministic checks when this flag is `False`.
3. **Crucial Fix:** Move the scoring logic to **after** the LLM assessment so the LLM's findings actually determine the score.

#### **Step 1: Modify `agents/safeguard/config.py**` [DONE]

Add the global control parameter.

```python
ENABLE_RULE_BASED_CHECKS = False

```

#### **Step 2: Modify `agents/safeguard/assessor.py**`

Update the `assess` method to respect the flag and fix the scoring order.

**Current Logic (Abstracted):**

```python
# 1. Run Rules -> checks/risks
# 2. Run Conditions -> checks/risks
# 3. Run Environment -> checks/risks
# 4. Calculate Score (based on 1-3)
# 5. Run LLM -> merge results (doesn't affect score)

```

**New Logic:**

```python
# 1. If ENABLE_RULE_BASED_CHECKS: Run Rules/Conditions/Environment
# 2. Run LLM -> merge results
# 3. Calculate Score (based on everything collected)

```

**Detailed Implementation Plan:**

1. **Import Config:**
```python
from agents.safeguard.config import ENABLE_RULE_BASED_CHECKS, get_DIET_SAFETY_RULES, ...

```


2. **Update `SafeguardAgent.assess` method:**

```python
    def assess(
        self,
        plan: Dict[str, Any],
        plan_type: str,
        user_metadata: Dict[str, Any],
        environment: Dict[str, Any] = {}
    ) -> SafetyAssessment:
        checks = []
        risk_factors = []

        # --- MODIFICATION START: Conditional Rule Execution ---
        if ENABLE_RULE_BASED_CHECKS:
            # 1. Run rule-based checks
            if plan_type == "diet":
                rule_checks, rule_risks = self._check_diet_safety(plan, user_metadata)
            elif plan_type == "exercise":
                rule_checks, rule_risks = self._check_exercise_safety(plan, user_metadata)
            else:
                rule_checks, rule_risks = [], []
            checks.extend(rule_checks)
            risk_factors.extend(rule_risks)

            # 2. Run condition-specific checks
            condition_checks, condition_risks = self._check_condition_restrictions(
                plan, plan_type, user_metadata
            )
            checks.extend(condition_checks)
            risk_factors.extend(condition_risks)

            # 3. Run environment checks
            env_checks, env_risks = self._check_environment_safety(
                plan, plan_type, environment
            )
            checks.extend(env_checks)
            risk_factors.extend(env_risks)
        # --- MODIFICATION END ---

        # 4. LLM semantic assessment (Always run or run if rules disabled)
        llm_assessment = self._llm_semantic_assessment(
            plan, plan_type, user_metadata, environment
        )

        # Merge LLM findings BEFORE scoring
        if llm_assessment:
            for rf_dict in llm_assessment.get("risk_factors", []):
                if isinstance(rf_dict, dict):
                    risk_factors.append(RiskFactor(**rf_dict))
            for check_dict in llm_assessment.get("checks", []):
                if isinstance(check_dict, dict):
                    checks.append(SafetyCheck(**check_dict))

        # --- MOVED SCORING LOGIC HERE ---
        
        # Calculate score based on ALL checks (Rules + LLM)
        passed_checks = sum(1 for c in checks if c.passed)
        total_checks = len(checks) if checks else 1 # Avoid div by zero

        # Base score
        if not checks:
            # If no checks ran at all (e.g. LLM failed and rules disabled), assume neutral/safe
            base_score = 100 
        else:
            base_score = (passed_checks / total_checks) * 100

        # Apply severity penalties from ALL risk factors (Rules + LLM)
        severity_penalty = 0
        for rf in risk_factors:
            penalty = {"low": 5, "moderate": 15, "high": 30, "very_high": 50}
            severity_penalty += penalty.get(rf.severity.value, 0)

        # Final score calculation
        final_score = max(0, min(100, base_score - severity_penalty))
        
        # ... remainder of the function (is_safe determination, status, return) ...

```