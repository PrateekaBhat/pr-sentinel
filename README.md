# PR Sentinel

**AI-Assisted Deployment Risk Assessment & Decision System for Pull Requests.**

PR Sentinel is an engineering platform that combines **deterministic rule-based scoring**, **repository documentation retrieval (RAG)**, and **role-based AI specialist reviewers (LangGraph)** to generate explainable deployment recommendations for pull requests.

Rather than relying on a black-box LLM to "guess" risk, PR Sentinel enforces a strict separation:
1. **The Deterministic Rule Engine calculates the risk score and detects evidence.**
2. **The LLM synthesizes repository context and explains production impact.**

---

## 🏛️ System Architecture

```
                                  GitHub PR URL
                                        │
                                FastAPI Backend
                                        │
                     ┌──────────────────┴──────────────────┐
                     │                                     │
               GitHub REST API                      Repository RAG
            (PR metadata, diff,                (README/docs → chunks
             commits, file tree)                 → nomic-embed-text
                     │                           → ChromaDB → top-k)
                     │                                     │
                     └──────────────────┬──────────────────┘
                                        │
                         Deterministic Risk Heuristics
                       (Auth, Data Layer, CI/CD, Secrets,
                        Deleted Tests → Weighted Score Math)
                                        │
                          LangGraph Multi-Agent Pipeline
          ┌────────────────┬────────────────┬────────────────┬────────────────┐
          │                │                │                │                │
    Security Eng     Backend Eng      Platform Eng      API Eng          QA Eng
      (auth/,        (migrations,       (k8s, ci,        (routes,      (*.test.*,
      secrets)        data layer)       docker)          api/)          *.spec.*)
          └────────────────┴────────────────┴────────────────┴────────────────┘
                                        │
                              Coordinator Node (LLM)
                       Synthesizes deterministic evidence +
                       agent findings + RAG citations → report
                                        │
                              Judge (LLM-as-Judge)
                       Checks every claim in the report traces
                             back to empirical evidence
                                        │
                        React + TypeScript Dashboard &
                        GitHub PR Comment / Markdown Artifact
```

---

## ⚡ Core Engineering Principles

### 1. Deterministic-First Risk Scoring
Risk scores are calculated via pure, auditable rule math. No magic LLM numbers:

Total Score = Base Risk (0) + Sum of Triggered Rule Weights (Capped at 100)

- **Authentication Logic Touched**: `+40`
- **Database Migrations / Schema**: `+35`
- **CI/CD Workflow Modified**: `+20`
- **No Test Files Touched**: `+10`
- **Large Diff (800+ lines changed)**: `+20`

### 2. Intent-Based Category Classification
Files are classified using path conventions and persistence-layer guards. Internal domain models (`models.py`, Pydantic classes) are categorized under **Application/Core Logic**, while files with explicit persistence signals (`alembic/`, `migrations/`, `.sql`, `prisma`) are categorized under **Data Layer**.

### 3. Role-Based Multi-Agent Routing (LangGraph)
Specialist agents mirror real software review roles (`Security Engineer`, `Backend Engineer`, `Platform Engineer`, `API Eng`, `QA Eng`). If a PR touches no files in an agent's domain, the agent **skips the LLM call entirely** (`0ms`, 0 tokens).

### 4. Review Effort Estimation
Calculates estimated human review time (`5 min`, `15 min`, `30 min`, `1 hour`, `2 hours`) deterministically based on line diff magnitude, subsystem spread, and calculated risk level.

---

## 🚀 Running Locally

PR Sentinel runs 100% locally and free via **Ollama** and **ChromaDB**:

### 1. Setup Local LLM (Ollama)
```bash
ollama pull llama3.2          # 3B chat model used by specialist agents, coordinator & judge
ollama pull nomic-embed-text  # Embedding model used for local repository RAG
```

### 2. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python test_workflow.py --repo PrateekaBhat/pr-sentinel --pr 2
```

### 3. Run Unit & Regression Tests
```bash
python -m pytest engine/tests/test_risk_engine.py engine/tests/test_category_classifier.py -v
```

---

## 🎯 Interview Talking Points & Design Decisions

- **Why deterministic rules + LLM synthesis?** Asking an LLM to evaluate code risk without deterministic grounding leads to hallucinated scores. Deterministic rules establish the baseline; the LLM adds human-readable production context and rollout recommendations.
- **Why LangGraph instead of a single prompt?** A single prompt holding 5 reviewer perspectives suffers from context degradation. Multi-agent routing isolates diff slices, enables zero-token skips for untouched domains, and provides auditable agent decisions.
- **Why ChromaDB RAG?** RAG grounds recommendations in the repository's own documented conventions (e.g. deployment guides, security policies) rather than generic LLM assumptions.

---

*PR Sentinel is built for Engineering Managers, Staff Engineers, and Developer Productivity teams looking for explainable, production-ready deployment decision tooling.*
