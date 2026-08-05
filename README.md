# PR Sentinel

**AI-assisted deployment risk assessment for pull requests.**

Paste a public GitHub PR URL. PR Sentinel fetches the diff, scores it with deterministic
heuristics, retrieves relevant context from the repo's own docs (RAG), routes the changed
files to five specialist agents, and has a coordinator synthesize everything into one
report — overall risk, rollout recommendation, and testing gaps — with a judge pass that
checks the report's claims are actually grounded in evidence.

Runs entirely on your own machine via [Ollama](https://ollama.com) — no Anthropic/OpenAI
account, API key, or per-request cost required.

## Architecture

```
                 GitHub PR URL
                      │
              FastAPI backend
                      │
         ┌────────────┴────────────┐
         │                         │
   GitHub REST API          Repository RAG
 (PR metadata, diff,      (README/docs → chunks
  commits, repo tree)      → Ollama embeddings
         │                  → ChromaDB → top-k)
         │                         │
         └────────────┬────────────┘
                      │
         Deterministic risk heuristics
     (auth/, payment/, config/, migrations,
        deleted tests → weighted score)
                      │
              LangGraph coordinator
      ┌────────┬────────┬────────┬────────┐
      │        │        │        │        │
 Security  Performance Database   API    Tests
  Agent      Agent      Agent    Agent   Agent
  (auth/,    (cache/,  (migrations/, (routes/, (*.test.*,
  payment/)  queue/)    schema/)     api/)     *.spec.*)
      └────────┴────────┴────────┴────────┘
                      │
              Coordinator (LLM)
        synthesizes heuristics + agent
       findings + RAG citations → report
                      │
              Judge (LLM-as-judge)
        checks every claim in the report
         traces back to real evidence
                      │
           React + TypeScript dashboard
```

Each agent only ever sees the files matching its own domain — the Security agent never
sees test files, the Database agent never sees route handlers. If a PR touches no files
in an agent's domain, that agent **skips the LLM call entirely** and reports
`applicable: false`. This is what makes the multi-agent split real rather than
decorative: five agents on a docs-only PR cost one API call's worth of latency, not five.

## Why this design

An earlier version of this project was a single prompt: "here's the diff, tell me the
risk." That's an AI wrapper around GitHub — anyone could paste the same diff into
ChatGPT. Three changes make it a system instead:

1. **The LLM never invents the risk score.** `heuristics.py` computes a deterministic,
   weighted score from concrete signals (auth files touched, tests deleted, migration
   added, diff size) *before* any model runs. The model explains and contextualizes that
   score; it doesn't set it.
2. **Retrieval grounds the analysis in this specific repo**, not general knowledge of
   what "auth code" usually looks like. If the repo's own docs say "changes to `auth/`
   require a canary rollout," the coordinator can cite that — a generic LLM call never
   could.
3. **Different risk domains get different context and different agents.** Security,
   database, API-compatibility, and test-coverage concerns don't share a review
   checklist in real engineering orgs, so they don't share one prompt here either. A
   coordinator merges structured findings rather than one model trying to hold five
   domains in its head at once.

If asked "why RAG instead of putting the whole repo in the prompt?": retrieval keeps the
context small and relevant regardless of repo size, and it's incremental — the index is
built once per repo and reused, not rebuilt (and re-paid-for, on a hosted model) on every
PR. If asked "why multiple agents instead of one bigger prompt?": each domain has
different evaluation criteria and only needs a slice of the diff, so routing reduces both
noise and token cost, and it's what lets an agent skip work entirely when it's not
relevant. If asked "why ChromaDB instead of FAISS?": persistence and metadata filtering
without standing up a separate service — a local file store fits a single-repo-at-a-time
tool better than an in-memory index rebuilt every run.

**What I deliberately didn't build:** MCP wrappers, a chat interface, dynamic tool-calling
by the model, and a repository knowledge graph. Each is a legitimate idea, but none of
them solve a problem this project actually has yet — see "What I'd build next" below for
where they'd fit if the project grew.

## Project structure

```
pr-sentinel/
├── backend/
│   ├── app/
│   │   ├── main.py              API routes — wires everything below together
│   │   ├── github_client.py     GitHub REST API: PR data, repo tree, raw file fetch
│   │   ├── heuristics.py        Deterministic risk scoring rules
│   │   ├── agent_routing.py     Maps changed files → agent domains by pattern
│   │   ├── ollama_client.py     Shared Ollama chat (JSON mode) + embeddings client
│   │   ├── ai_analyzer.py       Heuristics-only fallback analysis (used if Ollama is down)
│   │   ├── rag/
│   │   │   ├── doc_fetcher.py   Finds README/CONTRIBUTING/docs in the repo tree
│   │   │   ├── store.py         Chunks, embeds, indexes/queries ChromaDB
│   │   │   └── retriever.py     Ties fetch + index + query into one call
│   │   ├── agents/
│   │   │   ├── prompts.py       System prompts for each agent, coordinator, judge
│   │   │   ├── nodes.py         Agent / coordinator / judge node implementations
│   │   │   ├── state.py         Shared LangGraph state shape
│   │   │   └── graph.py         Builds the StateGraph: 5 agents → coordinator → judge
│   │   ├── demo_data.py         Curated demo PRs (offline gallery, no Ollama required)
│   │   └── models.py            Shared Pydantic schemas
│   └── requirements.txt
├── frontend/                    React + TypeScript + Tailwind (Vite)
│   └── src/components/          RiskGauge, AgentFindingsPanel, CitationsList, JudgeBadge, …
└── docker-compose.yml           ollama + backend + frontend, with a persisted Chroma volume
```

## Running it locally

**0. Install Ollama and pull the models** (one-time setup)

Download Ollama from [ollama.com/download](https://ollama.com/download), then:

```bash
ollama pull llama3.2            # chat model — used by every agent + the coordinator + judge
ollama pull nomic-embed-text    # embedding model — used to index repo docs for RAG
ollama serve                    # starts the local server on :11434 (often already running)
```

**1. Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

### Local workflow test helper

From the `backend` directory you can run a single local smoke test that exercises the same CLI flow your GitHub Action will use:

```bash
cd backend
python test_workflow.py --repo "owner/repo" --pr 123 --token "$GITHUB_TOKEN"
```

This will:
- run `backend/cli.py analyze`
- write `reports/report.json`
- write `reports/report.md`
- exit `1` if `report.decision == BLOCK`
- exit `0` otherwise

**2. Frontend**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173`. Paste a public GitHub PR URL (e.g.
`https://github.com/langchain-ai/langchain/pull/12345`), or click one of the curated
demo cards to see the full dashboard — including sample agent findings, citations, and a
judge verdict — instantly, with no backend calls required.

**Or with Docker** (spins up Ollama, the backend, and the frontend together):

```bash
docker compose up --build
# in a second terminal, pull both models into the Ollama container the first time:
docker compose exec ollama ollama pull llama3.1
docker compose exec ollama ollama pull nomic-embed-text
```

Frontend at `http://localhost:3000`, backend at `http://localhost:8000` (see
`http://localhost:8000/docs` for interactive API docs), Ollama at `http://localhost:11434`.
The RAG index persists in a named Docker volume so repos aren't re-embedded on restart.

### Choosing a model

Bigger models give more reliable structured JSON and better reasoning, but need more
RAM/VRAM and are slower on CPU-only machines — and this pipeline makes up to 7 LLM calls
per PR (5 agents + coordinator + judge, minus any agents skipped as not applicable), so
model speed matters more here than in a single-prompt tool. Set `OLLAMA_MODEL` in
`backend/.env`:

| Model | Size | Notes |
|---|---|---|
| `llama3.2` | ~3B | Fastest, runs on a laptop CPU, JSON output less consistent |
| `llama3.1` | ~8B | Good default balance of speed and quality |
| `mistral` | ~7B | Fast alternative to llama3.1 |
| `llama3.1:70b` | ~70B | Best quality, needs a strong GPU / lots of RAM |

Local models occasionally drift from the requested JSON schema — every LLM call in this
pipeline (agents, coordinator, judge) parses defensively, and if the coordinator call
itself fails outright, the whole request falls back to a heuristics-only result (with the
reason shown in the UI) rather than crashing.

## API

`POST /api/analyze` — body `{ "pr_url": "https://github.com/owner/repo/pull/123" }`,
returns the full `AnalyzeResponse`: PR metadata, heuristic scores, RAG context (citations
+ what was indexed), the AI analysis (including every agent's findings), and the judge's
groundedness verdict.

`GET /api/demos` / `GET /api/demos/{id}` — curated demo PRs, precomputed, no Ollama
required.

`GET /api/health` — reports which Ollama models and RAG settings are configured.

No GitHub OAuth is required — only the GitHub REST endpoints that work unauthenticated
against public repos. An optional `GITHUB_TOKEN` raises the rate limit from 60 to 5,000
requests/hour (this pipeline makes more GitHub calls than before, since it also walks the
repo tree for RAG — a token is worth setting).

## What I'd build next

Roughly in order of how much they'd actually improve the analysis, not how novel they'd
look on a resume:

- **Repository knowledge graph** — model service-to-service dependencies (e.g. "Payment
  Service → Database → Kafka → Notification"), so touching one file surfaces *downstream*
  blast radius, not just the file's own domain.
- **Memory across PRs** — "this repo usually pairs auth changes with integration tests;
  this PR deviates from that pattern" requires remembering the last N analyses per repo,
  not just this one.
- **Dynamic tool-calling** — instead of always running all 5 agents and always retrieving
  RAG context upfront, let the coordinator decide what it needs (fetch linked issue,
  compare with the last release, search architecture docs) and call for it.
- **MCP GitHub server** instead of the bespoke `github_client.py` — legitimate once the
  tool needs more GitHub surface area (issues, previous PRs, releases) than a couple of
  REST endpoints.

## Talking points for interviews

This project touches: RAG (chunking, embeddings, vector retrieval, and *why* retrieval
over stuffing the whole repo in-context), multi-agent orchestration with LangGraph
(parallel fan-out/fan-in, and routing that actually skips irrelevant agents rather than
running all of them regardless), LLM-as-judge for self-verification, combining
deterministic rules with LLM reasoning so the model explains a score instead of inventing
one, schema validation with Pydantic across a multi-step pipeline, running LLMs locally
via Ollama versus a hosted API and the cost/latency/reliability tradeoffs that come with
it, graceful degradation at every layer (RAG, individual agents, the coordinator) so a
missing dependency degrades the report instead of crashing it, and containerized
deployment with Docker Compose.
