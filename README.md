# PR Sentinel

**AI-powered pull request risk analysis for engineering teams.**

Paste a public GitHub PR URL. PR Sentinel fetches the diff, runs it through a set of
deterministic risk heuristics, then hands both to Claude for a reasoned assessment —
overall risk, architectural impact, a rollout recommendation, and testing gaps —
rendered on a dashboard designed to be read in five seconds during a merge review.

```
GitHub PR URL
      │
      ▼
FastAPI backend ── GitHub REST API (metadata, changed files, diff, commits)
      │
      ├── Deterministic heuristics (auth/, payment/, config/, migrations, deleted tests…)
      └── Local LLM via Ollama — reasons over the diff + heuristic signals,
          returns structured JSON (risk, rollout strategy, test gaps, file hotspots)
      │
      ▼
React + TypeScript dashboard
```

AI analysis runs entirely on your own machine via [Ollama](https://ollama.com) —
no Anthropic/OpenAI account, API key, or per-request cost required.

## Why this exists

Most PR tooling reviews *code style*. PR Sentinel asks a different question: **given
this diff, what could go wrong in production, and how should we roll it out?** That's
the question a Staff Engineer asks in a merge review, not a linter.

It combines two layers deliberately:

- **Heuristics first** — fast, free, deterministic rules (touching `auth/`, deleting
  tests, adding a migration, etc.) that don't depend on an LLM call succeeding.
- **AI second** — a local model (via Ollama) reads the actual diff plus the heuristic
  findings and explains *why* it matters, in plain English, with a structured JSON
  contract the frontend can render reliably.

If Ollama isn't running, isn't reachable, or the model isn't pulled yet, the backend
still returns a full report using heuristics alone, along with a banner explaining
why — the app never hard-fails just because the local model isn't wired up yet.

## Project structure

```
pr-sentinel/
├── backend/          FastAPI service (Python)
│   ├── app/
│   │   ├── main.py            API routes
│   │   ├── github_client.py   GitHub REST API client + URL parsing
│   │   ├── heuristics.py      Deterministic risk rules
│   │   ├── ai_analyzer.py     Ollama prompt + response parsing
│   │   ├── demo_data.py       Curated demo PRs for a fast, offline gallery
│   │   └── models.py          Shared Pydantic schemas
│   └── requirements.txt
├── frontend/          React + TypeScript + Tailwind (Vite)
│   └── src/
│       ├── components/        RiskGauge, FileRiskList, RolloutCard, …
│       └── api/client.ts       Typed fetch wrapper around the backend
└── docker-compose.yml
```

## Running it locally

**0. Install Ollama and pull a model** (one-time setup)

Download Ollama from [ollama.com/download](https://ollama.com/download), then:

```bash
ollama pull llama3.1     # ~4.7GB. See backend/.env.example for lighter/heavier options.
ollama serve             # starts the local server on :11434 (often already running in the background)
```

**1. Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # defaults already point at localhost:11434 / llama3.1
uvicorn app.main:app --reload
```

**2. Frontend**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173`. Paste a public GitHub PR URL (e.g.
`https://github.com/langchain-ai/langchain/pull/12345`), or click one of the curated
demo cards to see the dashboard instantly without waiting on GitHub or the model.

**Or with Docker** (spins up Ollama, the backend, and the frontend together):

```bash
docker compose up --build
# in a second terminal, pull the model into the Ollama container the first time:
docker compose exec ollama ollama pull llama3.1
```

Frontend at `http://localhost:3000`, backend at `http://localhost:8000` (see
`http://localhost:8000/docs` for interactive API docs), Ollama at
`http://localhost:11434`.

### Choosing a model

Bigger models give more reliable structured JSON and better reasoning, but need more
RAM/VRAM and are slower on CPU-only machines. Set `OLLAMA_MODEL` in `backend/.env`:

| Model | Size | Notes |
|---|---|---|
| `llama3.2` | ~3B | Fastest, runs on a laptop CPU, JSON output less consistent |
| `llama3.1` | ~8B | Good default balance of speed and quality |
| `mistral` | ~7B | Fast alternative to llama3.1 |
| `llama3.1:70b` | ~70B | Best quality, needs a strong GPU / lots of RAM |

Local models occasionally drift from the requested JSON schema — the backend parses
defensively and falls back to a heuristics-only result (with the reason shown in the
UI) rather than crashing when that happens.

## API

`POST /api/analyze` — body `{ "pr_url": "https://github.com/owner/repo/pull/123" }`,
returns the full `AnalyzeResponse` (PR metadata, heuristic scores, and the AI
analysis).

`GET /api/demos` — list of curated demo PRs.
`GET /api/demos/{id}` — full precomputed `AnalyzeResponse` for one demo.

No GitHub OAuth is required — only the GitHub REST endpoints that work
unauthenticated against public repos. An optional `GITHUB_TOKEN` raises the rate
limit from 60 to 5,000 requests/hour. No Anthropic/OpenAI account is required either
— AI analysis runs locally through Ollama.

## What I'd build next

- Compare risk between two PRs (e.g. a hotfix vs. the PR it's patching)
- Historical risk trends across a repo over time
- Click-through explainability: link each risk factor to the exact diff hunk that
  triggered it
- A generated release checklist tailored to the specific PR
- GitHub App / webhook integration to post the risk report as a PR comment on open

## Talking points for interviews

This project touches: REST API integration, prompt engineering for structured
(JSON) output, combining deterministic rules with LLM reasoning (and why that's more
trustworthy than an LLM alone), schema validation with Pydantic, running an LLM
locally (Ollama) versus a hosted API — and the resulting tradeoffs around cost,
latency, and output reliability — a typed React/TS frontend consuming a typed
backend contract, graceful degradation when a dependency (the local model) isn't
reachable, and containerized deployment with Docker Compose.
