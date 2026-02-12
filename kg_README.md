<h1 align="center">
A metabolic world model system for personalised lifestyle medicine
</h1>

<p align="center">
<strong>A framework for generating personalized, clinically safe diet and exercise interventions for metabolic management.</strong>
</p>

<p align="center">
<a href="#metabolic-knowledge-graph">Knowledge Graph</a> •
<a href="#lifestyle-prescription-generation">Generation Module</a> •
<a href="#clinical-security-module">Security Module</a> •
<a href="#quick-start">Quick Start</a>
</p>

<div align="center">
</div>

## Overview

To ensure the safety and effectiveness of diet and exercise prescriptions for metabolic management, this project implements a **knowledge-graph guided lifestyle prescription generation module**. By bridging the gap between open-ended LLM capabilities and practical clinical applicability, the system produces personalized interventions grounded in authoritative medical protocols.

The framework consists of three core components: a **Hybrid Metabolic Knowledge Graph** for data grounding, a **Hierarchical Generation Module** for flexible yet structured planning, and a **Clinical Security Module** for rigorous safety auditing.

---

## Key Features

### 🧠 Metabolic Knowledge Graph (Construction & Embedding)

Constructed from a curated corpus of authoritative clinical sources—spanning behavioural self-management, precision nutrition, and physical activity protocols—our knowledge graph serves as the reliable backbone of the system.

* **DeepSeek-R1 Extraction:** Utilizes DeepSeek-R1 to systematically extract domain knowledge using **Chain-of-Thought (CoT)** steps. This resolves ambiguous references, identifies conditional dependencies, and filters unsupported statements.
* **Ontology-Constrained Schema:** Organizes data within a standardized schema designed to represent complex lifestyle factors and condition-dependent medical interactions.
* **Hybrid Graph–Vector Infrastructure:** Entities are encoded using **Qwen3-Embedding-8B** to generate dense semantic representations. These are indexed within the graph database, enabling efficient similarity-based search and robust integration of symbolic and semantic evidence.

### 📝 Lifestyle Prescription Generation

This module employs a **knowledge-aware prompting strategy** to synthesize actionable plans aligned with the user’s CGM data, clinical parameters, and environmental context.

* **Context-Aware Retrieval:** Performs targeted traversal and embedding similarity searches to retrieve explicitly and semantically related knowledge, injecting a linearized subgraph into the system prompt.
* **Hierarchical Generation Strategy:**
1. **Semantic Synthesis:** The module first generates a diverse array of structured "base plans" covering broad semantic variations.
2. **Numerical Expansion:** A rule-based parser systematically modulates key quantitative attributes to expand these templates.


* **Outcome:** Transforms high-level directives into an extensive solution space, exploring a wide spectrum of candidate prescriptions while maintaining strict alignment with user requirements.

### 🛡️ Clinical Security Module

To ensure clinical safety, we implement a robust auditing mechanism leveraging **Qwen3-8B** and the metabolic knowledge graph.

* **Strict Contextual Search:** Initiates audits via **exact keyword matching** (prioritizing precision over semantic similarity) extracted from physiological metadata to prevent ambiguity-driven errors.
* **Semantic Safety Auditor:** The LLM evaluates proposed plans against retrieved constraints to identify latent risks, hidden contraindications, unrealistic progressions, and environmental mismatches.
* **Deterministic Guardrails:** In parallel, the module enforces physiological constraints driven by numerical benchmarks, filtering out prescriptions that deviate from established safety thresholds.

---
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
