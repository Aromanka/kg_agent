### Knowledge Graph
- **Document Parsing**: Supports PDF, Word, Excel, TXT formats
- **Entity Relationships**: Extracts relationships such as diet-disease, food-taboos, exercise-precautions, etc.
- **Neo4j Storage**: Persistent storage of the knowledge graph

### Diet Recommendation (Diet Pipeline)
- **Multi-Strategy Generation**: Uses Mandatory Ingredient Injection mechanism to ensure ingredient diversity
- **Portion Variants**: Automatically generates Lite/Standard/Plus three portion versions
- **Safety Assessment**: Built-in risk assessment module to evaluate the safety of recommended plans

### Exercise Recommendation (Exercise Pipeline)
- **Diversified Exercises**: Randomly selects combinations of aerobic, strength, and flexibility training
- **Intensity Variants**: Automatically generates Lite/Standard/Plus three intensity versions
- **Pre/Post-Meal Constraints**: Supports specifying exercise timing before or after meals
- **Weather Adaptation**: Intelligently adjusts exercise types based on weather conditions
- **Safety Assessment**: Built-in risk assessment module to evaluate the safety of recommended plans

## Quick Start

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt
# Start Neo4j
net start Neo4j
# Build knowledge graph
python -m core.build_kg
# Import knowledge graph
python -m core.import_kg
```

### Run Recommendation Pipelines
```bash
# Diet recommendation (4 base plans × 3 portion variants = 12 variants)
python -m pipeline.diet_pipeline --bn 4 --vn 3
# Exercise recommendation (3 base plans × 3 intensity levels = 9 variants)
python -m pipeline.exer_pipeline --bn 1 --vn 1 --query "I want to do some exercise about back muscles in the gym."
```

## Configuration
Configure in `config.json`:
```json
{
    "neo4j": { # Neo4j configuration
        "uri": "bolt://127.0.0.1:7687",
        "username": "neo4j",
        "password": "your_password"
    },
    "api_model": { # Remote LLM API for knowledge graph setup
        "api_key": "your_api_key",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
    },
    "local_model_path": "" # Local LLM path for generation
}
```
