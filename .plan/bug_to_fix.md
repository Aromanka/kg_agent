1. Update Data Cleaning & Chunking (build_kg_deepseek.py) ✅ DONE
Replace the regex-free read and fixed chunking with cleaning and header-aware splitting.

Changes made:
- Added `import re`
- Added `clean_text()` function to remove citations and page numbers
- Added `split_text_by_headers()` function to split by Markdown headers (##)
- Updated main loop to use cleaning + header-aware splitting

2. Fix JSON Prompt & Parsing (build_kg_deepseek.py & diet_kg.py) ✅ DONE
Align the prompt with the JSON Object requirement.

Changes made:
- diet_kg.py: Updated schema to require `{"triplets": [...]}` format
- diet_kg.py: Updated DIET_VALID_RELS with 12 new relation types
- build_kg_deepseek.py: Updated parser to prioritize "triplets" key

---

3. Neo4j Schema Mismatch (BUG - DO NOT FIX YET)
   Symptoms:
   - Warnings: "label does not exist" for Disease, Restriction, Nutrient
   - Warnings: "relationship type does not exist" for Diet_Disease, Restriction_Disease, Nutrient_Disease
   - Warnings: "property key does not exist" for description, advice, amount
   - Result: Generated 0 candidates

   Possible Causes:
   a) Database is empty - Neo4j contains no data
   b) Different schema - Data was imported with different labels/types than expected
   c) Schema migration needed - Different project used different entity labels

   Files involved:
   - core/neo4j/query.py - Query patterns assume specific labels/properties
   - agents/diet/generator.py - KG queries for disease, food, nutrient data

   Investigation steps:
   1. Run `core/import_kg.py` to check DB stats and imported data
   2. Compare actual schema vs expected schema in query.py
   3. Check if data exists with different labels (e.g., Entity instead of Disease)

---

4. LLM JSON Parsing Failure (BUG - DO NOT FIX YET)
   Error: "Error generating diet candidate 1: Expecting value: line 1 column 1 (char 0)"
   Error: "Error generating diet candidate 2: Expecting value: line 1 column 1 (char 0)"

   Possible Causes:
   a) LLM returns empty response - API key invalid or quota exceeded
   b) LLM returns non-JSON text - Prompt not enforcing JSON mode properly
   c) Timeout or network error - LLM request failed silently
   d) JSON parsing error in try-except - Catching too broad exception

   Files involved:
   - agents/diet/generator.py - JSON parsing in generate_diet_candidates()
   - core/llm/client.py - LLM API calls

   Investigation steps:
   1. Add debug logging to print raw LLM response before parsing
   2. Check API key and quota in config.json
   3. Verify response_format={'type': 'json_object'} is set
   4. Check for empty strings or whitespace in LLM response
