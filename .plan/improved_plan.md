
# Requirement & Target:
## Detailed Task Explanation
In the process of querying knowledge graph and format the query result for plans generation, we currently use a paradigm that: 1. firstly categorize retrieved knowledge and relations; 2. format each category in the prompt. Now modify it to a easier, simpler, less redundant method: 1. firstly retrieve the knowledge entities and targets and their relations, but no need to categorize and just save all relations uniformly; 2. and then, just convert those entities and relations by a uniform pattern. The new version should be much more simpler than the old one.


## Core code:
@agents/diet/generator.py and @agents/exer/generator.py

For example in diet agent, current implementation is in 1. query_dietary_by_entity and 2. _format_dietary_entity_kg_context:
            entity_knowledge = self.query_dietary_by_entity(user_preference, use_vector_search=use_vector)
            entity_context = self._format_dietary_entity_kg_context(entity_knowledge)

We are currently using KG_FORMAT_VER to contrtol the format method in _format_dietary_entity_kg_context, but this is just a partial solution. Should use KG_FORMAT_VER for the whole generate() process.

# Detailed PLAN

### **Objective**

Replace the current redundant categorization logic (separating benefits, risks, conflicts, etc.) with a unified approach that retrieves and formats all entity relations uniformly. This will be controlled by a `KG_FORMAT_VER` flag introduced in the `generate()` process.

### **Files to Modify**

1. `agents/base.py` (Core Logic)
2. `agents/diet/generator.py` (Diet Agent Implementation)
3. `agents/exercise/generator.py` (Exercise Agent Implementation)

---

### **Step 1: Modify `agents/base.py` (DietAgentMixin & ExerciseAgentMixin)**

You will update the query and formatting methods in both Mixins to support a new `KG_FORMAT_VER` (e.g., `VER=3`).

#### **1. Update `DietAgentMixin**`

* **Method:** `query_dietary_by_entity(..., kg_format_ver=2)`
* **Change:** Add `kg_format_ver` as an argument.
* **Logic:**
* **If `kg_format_ver >= 3`:** Initialize a simplified result structure: `{"matched_entities": [], "relations": []}`.
* Inside the GraphRAG/Search loops, do **not** filter by relation type (Benefit/Risk/Conflict). Instead, append **all** valid relations found to the `relations` list as generic dictionaries: `{"head": entity_name, "relation": rel_type, "tail": tail}`.
* **Else (Legacy):** Keep the existing logic that sorts relations into `entity_benefits`, `entity_risks`, etc.




* **Method:** `_format_dietary_entity_kg_context(entity_knowledge, kg_format_ver=2)`
* **Change:** Add `kg_format_ver` as an argument (remove the hardcoded local variable).
* **Logic:**
* **If `kg_format_ver >= 3`:**
* Iterate through `entity_knowledge["relations"]`.
* Format strictly using a uniform pattern, e.g., `"- {head} {relation} {tail}"` (optionally replacing underscores in relations with spaces).
* Group them under a single header like `## Knowledge Graph Insights` or by Entity if desired, but avoid creating separate sections for "Benefits" vs "Risks".


* **Else (Legacy):** Keep the existing formatting logic.





#### **2. Update `ExerciseAgentMixin**`

* **Method:** `query_exercise_by_entity(..., kg_format_ver=2)`
* **Change:** Add `kg_format_ver` as an argument.
* **Logic:**
* **If `kg_format_ver >= 3`:** Similar to Diet, use `{"matched_entities": [], "relations": []}`.
* Capture `Targets_Entity`, `Recommended_Duration`, `Has_Benefit`, etc., all into the uniform `relations` list without distinct buckets.




* **Method:** `_format_exercise_entity_kg_context(entity_knowledge, kg_format_ver=2)`
* **Change:** Add `kg_format_ver` as an argument.
* **Logic:**
* **If `kg_format_ver >= 3`:** Iterate through the `relations` list and output the uniform string pattern.





---

### **Step 2: Modify `agents/diet/generator.py**`

* **Method:** `DietAgent.generate`
* **Change:** Define the version constant at the start of the method: `KG_FORMAT_VER = 3`.
* **Update Calls:**
* Update the call to `self.query_dietary_by_entity(...)` to pass `kg_format_ver=KG_FORMAT_VER`.
* Update the call to `self._format_dietary_entity_kg_context(...)` to pass `kg_format_ver=KG_FORMAT_VER`.





---

### **Step 3: Modify `agents/exercise/generator.py**`

* **Method:** `ExerciseAgent.generate`
* **Change:** Define the version constant at the start of the method: `KG_FORMAT_VER = 3`.
* **Update Calls:**
* Update the call to `self.query_exercise_by_entity(...)` to pass `kg_format_ver=KG_FORMAT_VER`.
* Update the call to `self._format_exercise_entity_kg_context(...)` to pass `kg_format_ver=KG_FORMAT_VER`.





---

### **Verification Checklist**

* [ ] `generate` methods in both agents define the version flag.
* [ ] `query` methods in `base.py` return the simplified dictionary structure (list of relations) when the new version is passed.
* [ ] `format` methods in `base.py` generate a single list of strings based on the simplified structure when the new version is passed.
* [ ] Backward compatibility is maintained for `KG_FORMAT_VER < 3` (optional, but good practice given the existing code structure).