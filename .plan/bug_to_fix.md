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
