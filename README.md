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
                     Validates whether report claims are grounded
                    in evidence; flags unsupported/speculative ones
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

## 🛡️ Failure Handling

The deterministic policy engine is the single source of truth for the release decision, so the pipeline degrades gracefully when the AI layer has problems:

- **LLM unavailable** (Ollama down/unreachable): the pipeline falls back to deterministic-only analysis. The report/CLI/API response is still produced, `ai_enabled` is `false`, and a policy note states the deterministic engine made the call.
- **A specialist agent fails**: that agent is marked skipped/errored in `agent_statuses`; the rest of the pipeline (other specialists, coordinator, deterministic policy) continues.
- **The groundedness judge fails or flags unsupported claims**: this affects explanation confidence only — it never changes `release_risk` or the ALLOW/NEEDS_REVIEW/BLOCK decision.
- **The analysis itself crashes** (bad input, unexpected exception): `backend/cli.py` exits with code `2`, which the GitHub Actions workflow treats as a hard CI failure — distinct from a deliberate `BLOCK` (exit `1`), which also fails CI but for a different, expected reason.

## 🐕 Dogfooding

PR Sentinel was run against its own pull requests as part of development. That exercise surfaced several real problems that are now fixed: demo fixtures that no longer matched the current Pydantic models, CI failure semantics that could mask a genuine crash as a passing workflow, and evidence-grounding gaps where the coordinator's narrative could drift from what the specialists and heuristics actually reported. The tests and prompt constraints in this repo exist largely because of what dogfooding turned up.

## ⚠️ Limitations

- File-path-based category classification is heuristic, not a static analyzer — it can miscategorize unconventional repository layouts.
- Explanation quality depends on the local Ollama model in use; smaller CI-friendly models (e.g. `llama3.2`) trade depth for speed.
- Repository RAG is only as good as the repository's own documentation — undocumented conventions won't be surfaced.
- "Evidence Confidence" is a qualitative tier (High/Medium/Low), not a calibrated statistical probability.
- The suggested rollout strategy (Standard/Canary/Blue-Green/Manual Approval) is advisory guidance for reviewers, not an automated deployment controller.

---

## 🎯 Interview Talking Points & Design Decisions

- **Why deterministic rules + LLM synthesis?** Asking an LLM to evaluate code risk without deterministic grounding leads to hallucinated scores. Deterministic rules establish the baseline; the LLM adds human-readable production context and rollout recommendations.
- **Why LangGraph instead of a single prompt?** A single prompt holding 5 reviewer perspectives suffers from context degradation. Multi-agent routing isolates diff slices, enables zero-token skips for untouched domains, and provides auditable agent decisions.
- **Why ChromaDB RAG?** RAG grounds recommendations in the repository's own documented conventions (e.g. deployment guides, security policies) rather than generic LLM assumptions.

---

*PR Sentinel is built for Engineering Managers, Staff Engineers, and Developer Productivity teams looking for explainable, production-ready deployment decision tooling.*
