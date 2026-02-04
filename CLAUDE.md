# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Knowledge Graph + LLM** based agent project for generating personalized health recommendations. The system has three core modules:

1. **diet_candidate_generator** - Generates diet plan candidates based on user metadata and knowledge graph
2. **exer_candidate_generator** - Generates exercise plan candidates based on user metadata and knowledge graph
3. **safeguard** - Risk assessment module that evaluates plan safety (0-100 score, True/False)

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start Neo4j database (Windows)
net start Neo4j
net stop Neo4j

# Run the FastAPI server
python kg/server_local.py

# Build knowledge graph from documents
python kg/build_kg_deepseek.py
```

## Architecture

```
Input Data (PDF/DOCX/Excel/TXT)
        ↓
build_kg_deepseek.py → Neo4j Knowledge Graph
        ↓
server_local.py (FastAPI) → LLM + KG Validation
        ↓
Output: diet/exercise candidates with safety assessment
```

### Data Flow (server_local.py)
1. Extract keywords from user question via LLM
2. Query Neo4j knowledge graph for relevant entities
3. Generate initial answer using LLM with KG context
4. Validate answer against KG facts (correct if conflicts found)

### Knowledge Graph Schema (build_kg_deepseek.py)
Extracts 10 relation types from documents:
- Diet_Disease, Food_Diet, Food_Disease, Amount_Food, Frequency_Food
- Method_Food, Nutrient_Disease, Restriction_Disease, Benefit_Food, Risk_Food

## API Endpoints

- `POST /api/chat` - Chat Q&A with KG validation
- `GET /api/graph` - Get entity relationships for visualization
- `GET /` - Web UI (reads templates/index.html)

## Input Format Standard

```json
{
  "user_metadata": {
    "age": 35,
    "gender": "male",
    "height_cm": 175,
    "weight_kg": 70,
    "medical_conditions": ["hypertension", "diabetes"],
    "dietary_restrictions": ["low_sodium"],
    "fitness_level": "intermediate"
  },
  "environment": {
    "weather": {"condition": "rainy", "temperature_c": 18},
    "time_context": {"date": "2024-03-15", "time_of_day": "morning", "season": "spring"}
  },
  "user_requirement": { "goal": "weight_loss", "intensity": "moderate" }
}
```

## Configuration

Configure API keys and database connection in `kg/server_local.py`:
- `DEEPSEEK_API_KEY` - DeepSeek LLM API key
- `NEO4J_URI`, `NEO4J_AUTH` - Neo4j database credentials

Place input documents in `kg/data/` for knowledge graph building.
