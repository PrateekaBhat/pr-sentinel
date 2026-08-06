# PR Sentinel — Release Risk Assessment

**Generated:** 2026-08-06 13:21:00 UTC  ·  **Repository:** [PrateekaBhat/pr-sentinel](https://github.com/PrateekaBhat/pr-sentinel/pull/2)  ·  **PR:** #2

### ✅ ALLOW — MEDIUM risk (score 40/100)

## Executive Summary

Heuristic-only analysis (Model 'llama3.1' isn't pulled yet. Run: `ollama pull llama3.1`): 2 risk signal(s) triggered across 27 changed file(s). This is a deterministic, rule-based assessment only — no LLM synthesis, specialist agent review, or repository context was available for this run.

| | |
|---|---|
| **Decision** | `ALLOW` |
| **Overall Risk** | `MEDIUM` |
| **Risk Score** | 40 / 100 |
| **Confidence** | Medium (55% — partial evidence) |
| **Estimated Review Effort** | ⏱️ `2 hours` |
| **Recommended Deployment** | `Canary` |

## Pull Request

- **Title:** Improve report
- **Author:** @PrateekaBhat
- **Branch:** `feature-refactor` → `main`
- **Language / Framework:** Python / Unknown
- **Files Changed:** 27 (+2809/-412)
- **Merge Status:** clean

## Architectural Impact

**Affected subsystems:** `CI/CD`, `Dependencies`, `Tests`, `Application/Core Logic`, `Documentation`

Start Ollama and pull a model (see backend/.env.example) for a full AI-generated assessment.

## Score Calculation Math

The overall risk score is calculated deterministically from triggered rule weights:

| Factor | Points | Rule / Evidence |
|---|---|---|
| Base Risk | `0` | Clean starting baseline |
| Infrastructure / deployment files changed | `+20` | Matched in .github/workflows/pr-sentinel.yml |
| Large diff (800+ line changes) | `+20` | 3221 lines changed across 27 files. |
| **Total Calculated Score** | **`40`** | |

## Risk Score Breakdown

| Category | Status | Score | Evidence |
|---|---|---|---|
| Authentication | `LOW` | 0/100 | 0 item(s) |
| API | `LOW` | 0/100 | 0 item(s) |
| Data Layer | `LOW` | 0/100 | 0 item(s) |
| Infrastructure | `LOW` | 0/100 | 0 item(s) |
| CI/CD | `LOW` | 12/100 | 1 item(s) |
| Dependencies | `LOW` | 10/100 | 1 item(s) |
| Secrets | `LOW` | 0/100 | 0 item(s) |
| Tests | `MEDIUM` | 20/100 | 1 item(s) |
| Application/Core Logic | `HIGH` | 100/100 | 13 item(s) |
| Documentation | `HIGH` | 30/100 | 1 item(s) |

<details><summary><strong>CI/CD</strong> — LOW (12/100)</summary>

1 file(s) touched in this category.

- **`.github/workflows/pr-sentinel.yml`** — LOW severity (Medium confidence)
  - _Why it matters:_ This file defines the CI/CD pipeline (modified, +20/−1 lines). Changes here affect how automated tests, builds, and deployments are triggered.
  - _Evidence:_
    ```diff
    -      OLLAMA_MODEL: llama3.1
    +      # llama3.1 (8B) is too slow for a CPU-only GitHub-hosted runner (2 vCPU) —
    +      # a single agent call can exceed its own timeout before it even finishes
    +      # loading the model. llama3.2 (3B) trades some analysis depth for something
    +      # that actually completes in CI; run a
    ```
  - _Recommended action:_ Dry-run the updated pipeline on a branch before merging to avoid breaking the main build.

</details>

<details><summary><strong>Dependencies</strong> — LOW (10/100)</summary>

1 file(s) touched in this category.

- **`frontend/package-lock.json`** — LOW severity (Medium confidence)
  - _Why it matters:_ This lock file was updated (modified, +0/−42 lines), indicating a dependency version change. Review the diff for removed packages or major version bumps that could introduce breaking changes or new vulnerabilities.
  - _Evidence:_
    ```diff
    -      "libc": [
    -        "glibc"
    -      ],
    -      "libc": [
    -        "glibc"
    -      ],
    ```
  - _Recommended action:_ Check the changelog/CVE feed for the bumped packages before approving.

</details>

<details><summary><strong>Tests</strong> — MEDIUM (20/100)</summary>

1 file(s) touched in this category.

- **`backend/engine/tests/test_category_classifier.py`** — MEDIUM severity (High confidence)
  - _Why it matters:_ 170 additions / 0 deletions in this file.
  - _Evidence:_
    ```diff
    +﻿from __future__ import annotations
    +
    +import pytest
    +from engine.categories import (
    +    _confidence_label,
    +    _is_persistence_layer_file,
    ```
  - _Recommended action:_ Add or restore coverage for the touched code paths before this ships.

</details>

<details><summary><strong>Application/Core Logic</strong> — HIGH (100/100)</summary>

13 file(s) touched in this category.

- **`backend/engine/agent_routing.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This file is part of the LangGraph agent pipeline (modified, +19/−1 lines). Changes here affect specialist-agent routing, prompts, or coordinator synthesis.
  - _Evidence:_
    ```diff
    -    "database": re.compile(r"(^|/)(migrations?|schema|models?|entity|repository)(/|\.)|\.sql$", re.I),
    +    # Database agent: only files with clear persistence-layer signals.
    +    # A plain models.py in engine/, app/, or backend/ is a Pydantic/domain model,
    +    # NOT a database model — it must not route to this agent
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/agents/nodes.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This file is part of the LangGraph agent pipeline (modified, +29/−2 lines). Changes here affect specialist-agent routing, prompts, or coordinator synthesis.
  - _Evidence:_
    ```diff
    +        confidence = int(data.get("confidence", 60))
    +        confidence = 0
    +            confidence=confidence,
    -    data = await chat_json(COORDINATOR_SYSTEM_PROMPT, _build_coordinator_prompt(state), timeout=180.0)
    +    try:
    +        data = await chat_json(COORDINATOR_SYSTEM_PROMPT, _build_coordinator_prompt(state),
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/agents/prompts.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This file is part of the LangGraph agent pipeline (modified, +38/−11 lines). Changes here affect specialist-agent routing, prompts, or coordinator synthesis.
  - _Evidence:_
    ```diff
    -  "risk_note": "<one sentence: does this domain add risk to this PR, and why>"
    +  "risk_note": "<one sentence: does this domain add risk to this PR, and why>",
    +  "confidence": <integer 0-100, how confident you are in this assessment given what you were shown>
    -say so plainly in risk_note — do not invent a problem to 
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/agents/state.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This file is part of the LangGraph agent pipeline (modified, +1/−0 lines). Changes here affect specialist-agent routing, prompts, or coordinator synthesis.
  - _Evidence:_
    ```diff
    +    coordinator_error: str
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/ai_analyzer.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This is a core implementation file (modified, +14/−5 lines). Review the changed logic in `ai_analyzer.py` for correctness and test coverage.
  - _Evidence:_
    ```diff
    +            executive_summary=data.get("executive_summary") or data.get("summary", ""),
    +            affected_subsystems=[str(x) for x in (data.get("affected_subsystems") or [])],
    -            rollout_strategy=data.get("rollout_strategy", "Standard merge"),
    +            rollout_strategy=data.get("rollout_strategy", "S
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/categories.py`** — HIGH severity (High confidence)
  - _Why it matters:_ 549 additions / 0 deletions in this file.
  - _Evidence:_
    ```diff
    +﻿from __future__ import annotations
    +
    +import re
    +from typing import Any
    +
    +from .models import (
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/demo_data.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This is a core implementation file (modified, +136/−30 lines). Review the changed logic in `demo_data.py` for correctness and test coverage.
  - _Evidence:_
    ```diff
    +from .categories import build_agent_decisions
    +    ArchitecturalImpact,
    +    ConfidenceExplanation,
    +    DeploymentRecommendation,
    +        report=RiskReport(
    +            decision="ALLOW",
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/heuristics.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This is a core implementation file (modified, +9/−3 lines). Review the changed logic in `heuristics.py` for correctness and test coverage.
  - _Evidence:_
    ```diff
    -    ("infra", "Infrastructure / deployment files changed", 30, re.compile(r"(^|/)(terraform|infra|deploy|docker|ci|\.github/workflows)(/|\.)", re.I)),
    +    # Reduced from 30 → 20: a CI/CD workflow change is lower risk than a genuine
    +    # IaC or deployment change (Terraform, Kubernetes, Docker). The workflow
    +    # h
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/models.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This file defines internal domain or data-transfer models (modified, +67/−6 lines). No ORM base classes, Alembic migrations, or persistence-layer signals were detected in this path—this is a Pydantic/dataclass domain model, not a database schema.
  - _Evidence:_
    ```diff
    -    score: float = 0.0  # similarity score, higher = more relevant
    +    score: float = 0.0  # cosine similarity score; positive = more relevant
    +    retrieval_reason: str = ""  # human-readable explanation of why this chunk was retrieved
    +    confidence: int = 60  # 0-100, how confident this agent is in its own findin
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/rag/retriever.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This is a core implementation file (modified, +37/−2 lines). Review the changed logic in `retriever.py` for correctness and test coverage.
  - _Evidence:_
    ```diff
    +def _infer_retrieval_reason(path: str, snippet: str) -> str:
    +    """Generate a human-readable explanation of why a document chunk was retrieved,
    +    based on its source path and a brief look at the snippet content."""
    +    path_lower = path.lower()
    +    if "readme" in path_lower:
    +        return "Describes the proje
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/report_renderer.py`** — HIGH severity (High confidence)
  - _Why it matters:_ 166 additions / 88 deletions in this file.
  - _Evidence:_
    ```diff
    +def _format_timestamp(raw: str) -> str:
    +    """Render an ISO-8601 timestamp (often with microseconds, e.g.
    +    '2026-08-06T10:04:37.276438+00:00') as a short, human-readable UTC
    +    string, e.g. 'Aug 6, 2026, 10:04 UTC'. Falls back to the raw value
    +    (trimmed to whole seconds) if parsing fails."""
    +    try:
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`backend/engine/service.py`** — LOW severity (Medium confidence)
  - _Why it matters:_ This file contains service-layer orchestration logic (modified, +67/−18 lines). Review for correctness of the changed business rules or data flow.
  - _Evidence:_
    ```diff
    +from .categories import (
    +    build_agent_decisions,
    +    build_architectural_impact,
    +    build_category_breakdown,
    +    build_confidence_explanation,
    +)
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.
- **`frontend/src/types.ts`** — LOW severity (Medium confidence)
  - _Why it matters:_ This is a core implementation file (modified, +73/−0 lines). Review the changed logic in `types.ts` for correctness and test coverage.
  - _Evidence:_
    ```diff
    +  cache_hit: boolean;
    +  indexed_doc_paths: string[];
    +  confidence: number;
    +}
    +
    +/** Surfaces one node's execution inside the LangGraph pipeline. */
    ```
  - _Recommended action:_ Review the logic change for correctness; ensure the affected code paths have test coverage.

</details>

<details><summary><strong>Documentation</strong> — HIGH (30/100)</summary>

1 file(s) touched in this category.

- **`backend/reports/report.md`** — HIGH severity (High confidence)
  - _Why it matters:_ 372 additions / 14 deletions in this file.
  - _Evidence:_
    ```diff
    -## PR Sentinel Report
    +# PR Sentinel — Release Risk Assessment
    -Overall Risk: RiskLevel.LOW
    +**Generated:** 2026-08-06 12:29:37 UTC  ·  **Repository:** [PrateekaBhat/pr-sentinel](https://github.com/PrateekaBhat/pr-sentinel/pull/2)  ·  **PR:** #2
    -Decision: ALLOW
    +### ✅ ALLOW — MEDIUM risk (score 50/100)
    ```
  - _Recommended action:_ No action required beyond a standard doc review.

</details>

## Agent Pipeline (LangGraph)

Each specialist agent only reviews files in its own domain; the coordinator agent
synthesizes their output (below) into the executive summary and risk breakdown above.

| Agent | Decision | Confidence | Time |
|---|---|---|---|
| Security | Skipped — no files in this agent’s domain were touched | High | 0ms |
| Database | Skipped — no files in this agent’s domain were touched | High | 0ms |
| API Compatibility | Skipped — no files in this agent’s domain were touched | High | 0ms |
| Test Coverage | No concerns raised | Low | 285ms |
| Performance | Skipped — no files in this agent’s domain were touched | High | 0ms |

<details><summary><strong>Security</strong> reasoning</summary>

No files in this domain were touched by this PR.

</details>

<details><summary><strong>Database</strong> reasoning</summary>

No files in this domain were touched by this PR.

</details>

<details><summary><strong>API Compatibility</strong> reasoning</summary>

No files in this domain were touched by this PR.

</details>

<details><summary><strong>Test Coverage</strong> reasoning</summary>

Agent call failed (Model 'llama3.1' isn't pulled yet. Run: `ollama pull llama3.1`); files were not analyzed by AI for this domain.

</details>

<details><summary><strong>Performance</strong> reasoning</summary>

No files in this domain were touched by this PR.

</details>

## Repository Context (RAG)

Indexed **0** repository document(s) into **5** chunk(s) from branch `main` (freshly indexed).

**Top repository context retrieved:**

#### `README.md`
**Why retrieved:** Describes the project architecture, component overview, and heuristic scoring pipeline.
```
base agent never sees route handlers. If a PR touches no files
in an agent's domain, that agent **skips the LLM call entirely** and reports
`applicable: false`. This is what makes the multi-agent split real rather than
decorative: five agents on a docs-only PR cost one API call's worth of latency, n...
```

#### `README.md`
**Why retrieved:** Describes the project architecture, component overview, and heuristic scoring pipeline.
```
# PR Sentinel

**AI-assisted deployment risk assessment for pull requests.**

Paste a public GitHub PR URL. PR Sentinel fetches the diff, scores it with deterministic
heuristics, retrieves relevant context from the repo's own docs (RAG), routes the changed
files to five specialist agents, and has a ...
```

#### `README.md`
**Why retrieved:** Describes the project architecture, component overview, and heuristic scoring pipeline.
```
y  Performance Database   API    Tests
  Agent      Agent      Agent    Agent   Agent
  (auth/,    (cache/,  (migrations/, (routes/, (*.test.*,
  payment/)  queue/)    schema/)     api/)     *.spec.*)
      └────────┴────────┴────────┴────────┘
                      │
              Coordinator (LLM)...
```

#### `README.md`
**Why retrieved:** Describes the project architecture, component overview, and heuristic scoring pipeline.
```
s deleted, migration
   added, diff size) *before* any model runs. The model explains and contextualizes that
   score; it doesn't set it.
2. **Retrieval grounds the analysis in this specific repo**, not general knowledge of
   what "auth code" usually looks like. If the repo's own docs say "changes...
```

#### `README.md`
**Why retrieved:** Describes the project architecture, component overview, and heuristic scoring pipeline.
```
│
              FastAPI backend
                      │
         ┌────────────┴────────────┐
         │                         │
   GitHub REST API          Repository RAG
 (PR metadata, diff,      (README/docs → chunks
  commits, repo tree)      → Ollama embeddings
         │                  → Ch...
```

## Deployment Recommendation

**Chosen strategy: `Canary`**

Based on deterministic rule score only; enable AI analysis for a reasoned recommendation.

- **Monitoring focus:** Monitor CI pipeline step completion, runner resource usage, and error rate during early deployment.
- **Rollback trigger:** Immediate rollback on any pipeline failure or unexpected workflow runner exit code.
- **Required approval:** `Platform / DevOps Lead`
- **Rollback plan required:** No

**Alternatives considered:**
- Standard (skipped — this touches a live code path)
- Blue/Green (more than this change warrants)

## Confidence

**Medium** (55% score) — partial evidence

Repository documentation was retrieved and used as context; the heuristic score and the LLM's risk assessment agree; the AI pipeline was unavailable; this is a deterministic heuristics-only assessment.

- Repository context available: Yes
- LLM and heuristic analyses agree: Yes

## Execution Metrics

- **Total duration:** 3.3s
- Repository Loaded: 1.5s
- Repository Context Retrieved: 1.2s
- Security: 0ms
- Database: 0ms
- API Compatibility: 0ms
- Test Coverage: 285ms
- Performance: 0ms
- Final Decision: 275ms

## Groundedness Check

**Verdict:** Grounded
- _Coordinator produced no output to judge._

> ⚠️ **Note:** AI analysis unavailable — this report reflects deterministic heuristics only.
> Model 'llama3.1' isn't pulled yet. Run: `ollama pull llama3.1`

---
*Generated by [PR Sentinel](https://github.com) — AI-powered deployment risk analysis.*