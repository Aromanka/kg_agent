# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**kg_agents** - A health recommendation system with two pipelines:
- **Diet Pipeline**: Generates meal recommendations with safety assessments
- **Exercise Pipeline**: Generates exercise plans with safety assessments

The system integrates LLMs (DeepSeek) with a Neo4j knowledge graph using GraphRAG (vector-based semantic search) for intelligent health recommendations.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start Neo4j first (required for knowledge graph operations)
net start Neo4j                    # Windows
./neo4j start                     # Linux

# Build knowledge graph from documents
python -m core.build_kg
python -m core.import_kg
python -m core.embed_kg           # Optional: embed knowledge graph

# Run pipelines directly
python -m pipeline.diet_pipeline --bn 1 --vn 5 --query "I want a vegetable sandwich" --use_vector --rag_topk 5
python -m pipeline.exer_pipeline --bn 1 --vn 4 --query "Back muscle training" --use_vector --rag_topk 5

# Run Flask API server
python server.py

# API endpoints:
# POST /api/v1/diet/generate-only - Diet recommendation
# POST /api/v1/safety/evaluate    - Safety assessment
```

### Pipeline Arguments
- `--bn`: Number of base plans to generate per meal/exercise type
- `--vn`: Number of variants (Lite/Standard/Plus) per base plan
- `--query`: User preference query
- `--use_vector`: Enable vector-based GraphRAG for semantic retrieval
- `--rag_topk`: Number of top-K results from GraphRAG (default: 3)

## Architecture

### Directory Structure
```
kg_agents/
├── agents/          # Agent implementations
│   ├── base.py      # BaseAgent abstract class, DietAgentMixin, ExerciseAgentMixin
│   ├── diet/        # DietAgent, models, config, parser
│   ├── exercise/    # ExerciseAgent, models, config, generator
│   └── safeguard/   # SafeguardAgent for safety assessment
├── core/            # Core infrastructure
│   ├── llm/         # LLMClient, local_llm utilities
│   └── neo4j/       # Neo4jClient, KnowledgeGraphQuery
├── pipeline/        # Pipeline orchestrators (diet, exercise, health)
├── kg/              # Knowledge graph prompts and templates
├── server.py        # Flask REST API server
└── config.json      # Configuration file
```

### Key Patterns

**Agent Architecture** (`agents/base.py`):
- `BaseAgent`: Abstract base class defining the agent interface
- `DietAgentMixin`: Provides diet-specific methods like `query_dietary_by_entity()`, `calculate_target_calories()`
- `ExerciseAgentMixin`: Provides exercise methods like `query_exercise_by_entity()`, `estimate_calories_burned()`
- Concrete agents inherit from `BaseAgent` and mixins as needed

**Pipeline Pattern** (`pipeline/`):
1. Generate candidates via LLM
2. Expand to portion/intensity variants (Lite/Standard/Plus)
3. Run safety assessment (rule-based or LLM-based)
4. Select top plans by safety score

**GraphRAG Pattern** (`core/neo4j/`):
1. Vector search (`search_similar_entities`) for semantic matching
2. Graph traversal (`get_neighbors`) for context expansion
3. Results formatted for LLM prompts

**Singleton Pattern**: Config loader (`config_loader.py`) and LLM client use lazy initialization singletons.

### Service Layer
`server.py` exposes Flask REST endpoints. Agents can also be used directly from Python via their `generate()` method with `AgentInput` dictionaries.

## Configuration

Configure in `config.json`:
```json
{
    "neo4j": { "uri": "bolt://127.0.0.1:7687", "username": "...", "password": "..." },
    "api_model": { "api_key": "...", "base_url": "...", "model": "deepseek-chat" },
    "local_model_path": "",      # Local LLM path (optional)
    "local_emb_path": ""         # Local embedding model path (optional)
}
```

Use `get_neo4j_config()`, `get_deepseek_config()`, or convenience lambdas like `NEO4J_URI()` from `config_loader.py`.

## Safety Assessment

Toggle rule-based checks in `agents/safeguard/config.py` via `ENABLE_RULE_BASED_CHECKS`:
- `True`: Fast rule-based validation
- `False` (default): LLM-based semantic safety assessment

## Knowledge Graph Relations

Common relation types in the Neo4j KG:
- `Has_Benefit` / `Indicated_For`: Positive effects
- `Has_Risk` / `Contraindicated_For`: Negative effects
- `Antagonism_With`: Conflicts
- `Targets_Entity`: Muscle targeting
- `Recommended_Duration` / `Recommended_Frequency`: Exercise guidelines
