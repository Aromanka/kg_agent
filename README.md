### Knowledge Graph
- **Document Parsing**: Supports PDF, Word, Excel, TXT formats
- **Entity Relationships**: Extracts relationships such as diet-disease, food-taboos, exercise-precautions, etc.
- **Neo4j Storage**: Persistent storage of the knowledge graph
- **GraphRAG**: Vector-based semantic search for retrieving relevant knowledge (use `--use_vector` flag)

### Diet Recommendation (Diet Pipeline)
- **Multi-Strategy Generation**: Uses Mandatory Ingredient Injection mechanism to ensure ingredient diversity
- **Portion Variants**: Automatically generates Lite/Standard/Plus three portion versions
- **Safety Assessment**: Built-in risk assessment module (LLM-first by default, rule-based optional via `ENABLE_RULE_BASED_CHECKS` in `agents/safeguard/config.py`)

### Exercise Recommendation (Exercise Pipeline)
- **Diversified Exercises**: Randomly selects combinations of aerobic, strength, and flexibility training
- **Intensity Variants**: Automatically generates Lite/Standard/Plus three intensity versions
- **Pre/Post-Meal Constraints**: Supports specifying exercise timing before or after meals
- **Weather Adaptation**: Intelligently adjusts exercise types based on weather conditions
- **Safety Assessment**: Built-in risk assessment module (LLM-first by default, rule-based optional via `ENABLE_RULE_BASED_CHECKS` in `agents/safeguard/config.py`)

## Quick Start

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install jdk on linux
# config java
export JAVA_HOME=/home/bml/storage/mnt/v-044d0fb740b04ad3/org/X_Life/kg_agents/packages/jdk-17.0.18
export JRE_HOME=${JAVA_HOME}/jre
export CLASSPATH=.:${JAVA_HOME}/lib:${JRE_HOME}/lib
export PATH=${JAVA_HOME}/bin:$PATH
# check java version
java -version

# Start Neo4j
net start Neo4j # windows
./neo4j start # Linux
# Build knowledge graph
python -m core.build_kg
# Import knowledge graph
python -m core.import_kg
# (Optional) Embedding knowledge graph
python -m core.embed_kg
```

### Run Recommendation Pipelines
```bash
# Diet recommendation with vector-based GraphRAG
python -m pipeline.diet_pipeline --bn 1 --vn 5 --query "I want to have a sandwich with only vegetables, no meat." --use_vector --rag_topk 5

# Exercise recommendation with vector-based GraphRAG
python -m pipeline.exer_pipeline --bn 1 --vn 4 --query "I want to do some exercise training back muscles in the gym." --use_vector --rag_topk 5
```

#### Pipeline Arguments
- `--bn`: Number of base plans to generate per meal/exercise type
- `--vn`: Number of variants (Lite/Standard/Plus) per base plan
- `--query`: User preference query (e.g., specific food or exercise request)
- `--use_vector`: Enable vector-based GraphRAG for semantic knowledge retrieval
- `--rag_topk`: Number of top-K results to retrieve from GraphRAG (default: 3)

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
        "base_url": "",
        "model": ""
    },
    "local_model_path": "", # Local LLM path for generation
    "local_emb_path": ""    # Local Embedding model path
}
```
