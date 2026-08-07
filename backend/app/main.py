from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from engine import demo_data
from engine.config import get_settings
from engine.github_client import GitHubError
from engine import history
from engine.models import AnalyzeRequest, AnalyzeResponse, DemoSummary
from engine.ollama_client import OllamaError
from engine.service import analyze_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pr_sentinel")

settings = get_settings()

app = FastAPI(
    title="PR Sentinel API",
    description="AI-powered pull request risk analysis for engineering teams.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": settings.ollama_model,
        "ollama_embed_model": settings.ollama_embed_model,
        "rag_enabled": settings.rag_enabled,
    }


@app.get("/api/demos", response_model=list[DemoSummary])
async def get_demos() -> list[DemoSummary]:
    return demo_data.list_demos()


@app.get("/api/demos/{demo_id}", response_model=AnalyzeResponse)
async def get_demo(demo_id: str) -> AnalyzeResponse:
    demo = demo_data.get_demo(demo_id)
    if demo is None:
        raise HTTPException(status_code=404, detail=f"No demo found with id '{demo_id}'")
    return demo


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return await analyze_request(request, token=settings.github_token)
    except GitHubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaError as exc:
        logger.warning("Ollama error in analysis endpoint: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/history")
async def get_history(limit: int = 50, repository: str | None = None) -> list[dict]:
    """Latest completed analyses, newest first. Optionally scoped to one
    repository (e.g. ?repository=acme/widgets)."""
    return history.get_history(limit=limit, repository=repository)


@app.get("/api/repository-health")
async def get_repository_health(repository: str | None = None, window: int = 100) -> dict:
    """Aggregate risk/confidence/deployment stats over recent analyses —
    powers the dashboard's Repository Health panel."""
    return history.get_repository_health(repository=repository, window=window)

