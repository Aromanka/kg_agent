<h1 align="center">
X-Life: A Metabolic World Model System
</h1>

<p align="center">
<strong>A closed-loop AI system for personalized lifestyle medicine, integrating metabolic world models, knowledge-graph guided agents, and mixed-reality deployment.</strong>
</p>

<p align="center">
<a href="## Installation">Installation</a> •
<a href="#1-metabolic-world-model">Metabolic World Model</a> •
<a href="#2-knowledge-graph-guided-agents">KG & Agents</a> •
<a href="#3-ar-deployment-x-ready">AR Deployment</a> •
<a href="#4-omics-integration">Omics</a> •
<a href="#citation">Citation</a>
</p>

<div align="center">
</div>

## Overview

**X-Life** is a multimodal framework capable of integrating continuous glucose monitoring (CGM), wearable sensor signals, self-reported behavioural information and contextual metadata  to deliver personalized lifestyle prescriptions in real time. 

---
# Hardware
### Equipment list

* CGM sensor
* Fit Bands (运动手环都有的功能写进来，写所有运动手环公司都要有)
* XREAL One Pro (XREAL, China) 

---
# Software
## Setup
The metabolic world model are developed using Python 3.10, Pytorch 2.6 and JDK-17.0.18, and are trained on Ubuntu 20.04 with NVIDIA A800 SXM4 80 GB. The AR system is developed and packaged using Unity3D (需要写unity版本) compatible with a Windows10 system(兼容哪些版本？). 
## Installation

We recommend using `conda` to manage the environment and dependencies.

1. **Clone the repository:**
```bash
git clone (改为github连接)
cd (改为repo_name)
```


2. **Create and activate the environment:**
```bash
conda create -n xlife python=3.10 -y
conda activate xlife
```


3. **Install python dependencies:**
```bash
pip install -r requirements.txt
```


4. **Install Neo4j Service:**
```bash
# Install JDK
sudo apt install openjdk-11-jdk
# check the version of the installed JDK
java -version
```

Download the latest Neo4j tarball from [Neo4j Deployment Center](https://neo4j.com/deployment-center/?gdb-selfmanaged) and start the service:
```bash
tar zxf neo4j-community-5.26.21-unix.tar.gz
cd neo4j-community-5.26.21/bin/
./neo4j start
```

---

## 1. Metabolic World Model

The **Metabolic World Model (MWM)** serves as the physiological simulation engine of the X-Life system. Built upon a robust **Time-Series Transformer** architecture, the MWM is designed to learn the complex, non-linear dynamics of human glucose metabolism from large-scale observational data.

### Key Capabilities

* **Deep Generative Modeling:** Trained on over 460 million CGM time-points, the model captures long-term dependencies and individual glycemic variability with high fidelity.
* **Counterfactual Inference:** Unlike standard forecasting models, the MWM acts as a "digital twin," allowing users to simulate *what-if* scenarios (e.g., "What happens to my glucose if I switch this meal to a salad?"). This capability enables the system to evaluate the physiological impact of potential diet and exercise plans before prescription.
* **State-Space Tracking:** The model maintains a latent metabolic state, updating continuously based on incoming physiological streams to provide personalized, time-varying predictions.


1. Data Preparation
```bash
```
2. Training Model
```bash
```
3. Evaluate Model
```bash
```

---

## 2. Knowledge-Graph Guided Agents

The Knowledge-Graph Guided Agents `./kg_agents/` generate personalized diet and exercise prescriptions by grounding LLM outputs in a hybrid vector-graph metabolic knowledge base, safeguarded by a security module that enforces clinical safety through semantic auditing and deterministic constraints.


### Knowledge-Graph Configuration
Configure Neo4j database, remote LLM API and local models in `./kg_agents/config.json`:
```json
{
    "neo4j": { # Neo4j configuration
        "uri": "bolt://127.0.0.1:7687",
        "username": "your_username",
        "password": "your_password"
    },
    "api_model": { # Remote LLM API for knowledge graph setup
        "api_key": "your_api_key",
        "base_url": "your_base_url",
        "model": "your_api_model"
    },
    "local_model_path": "your_local_LLM_path", # Local LLM path for generation
    "local_emb_path": "your_local_embedding_model_path" # Local Embedding model path for RAG
}
```

### Setup Knowledge Graph
1. Prepare guidelines following the descriptions in our paper.
```bash
.
├── data/
│   ├── diet/
│   │   ├── diet_guideline_1.pdf
│   │   └── ...
│   │
│   └── exer/
│       ├── exer_guideline_1.pdf
│       └── ...
```
Extract and embed entities (Make sure the Neo4j server has started):
```bash
cd kg_agents
# Extract knowledge from ./data
python -m core.build_kg
# Import knowledge graph
python -m core.import_kg
# (Optional) Embedding knowledge graph
python -m core.embed_kg
```


### Test Generation & Assessment Pipelines
```bash
# Test diet prescription pipeline
python -m pipeline.diet_pipeline --bn 1 --vn 5 --query "I want a sandwich with just veggies, no meat." --use_vector --rag_topk 5
# Test exer prescription pipeline
python -m pipeline.exer_pipeline --bn 1 --vn 4 --query "I want to do some back exercises at the gym." --use_vector --rag_topk 5
```
Pipeline Arguments:
- `--bn`: Number of base plans to generate by LLM.
- `--vn`: Number of variants per base plan.
- `--query`: User user preference query.
- `--use_vector`: Enable vector-based GraphRAG.
- `--rag_topk`: Number of top-K results to retrieve from GraphRAG.


### Start Flask service:
```bash
python server.py
```
Test service interfaces:
```bash
# diet prescriptions generation
curl -X POST http://localhost:5000/api/v1/diet/generate-only -H "Content-Type: application/json" -d '{args}'
# exercise prescriptions generation
curl -X POST http://localhost:5000/api/v1/exercise/generate-only -H "Content-Type: application/json" -d '{args}'
# security module assess prescription
curl -X POST http://localhost:5000/api/v1/safety/evaluate -H "Content-Type: application/json" -d '{
    "plan_type": "diet/exercise",
    "user_metadata": {detailed_metadata},
    "plan": {plan_to_assess}
}'
```
---

## 3. AR Deployment
（这块需要孙乐提供）
**X-Ready** represents the deployment interface of the X-Life system, integrating the metabolic agent into a physical mixed-reality environment. By leveraging smart glasses (e.g., Ray-Ban Meta) and large multi-modal models (LMMs), X-Ready facilitates real-time, context-aware interaction.

* **Egocentric Vision Analysis:** The system captures first-person view images to identify real-world entities (e.g., food items, exercise equipment) and estimate nutritional content or activity intensity in real-time.
* **Context-Aware Guidance:** Metabolic insights and agent suggestions are overlaid audibly or visually, providing immediate feedback (e.g., "This meal may spike your glucose; consider a walk afterwards") without disrupting the user's daily routine.

### Deployment
To deploy the AR system, download our compiled package from google drive [AR package](www.baidu.com), and install it on (写好系统版本):
```bash
```

---

## 4. Omics Integration
(这块可能需要按照组学代码修改，这里我让AI乱写的)
As a supplementary layer for enhanced personalization, X-Life supports the integration of multi-omics data. The system can ingest **gut microbiome profiles** and **metabolomics data** to refine its predictive accuracy. By correlating specific bacterial strains (e.g., *P. copri*) and metabolic markers with glycemic responses, the model can tailor interventions to the user's unique biological microbiome signature.

### Omics Data Preparation
```bash
```
### Training Model
```bash
```
### Evaluate Model
```bash
```

---

## Citation

If you use this code or dataset in your research, please cite our paper:

```bibtex
@article{XLife2026,
  title = {X-Life: A metabolic world model system for personalised lifestyle medicine},
  author = {Wu, Qian and Qin, Yiming and et al.},
  journal = {},
  year = {2026}
}

```