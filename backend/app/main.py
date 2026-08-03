from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import demo_data, github_client, heuristics
from .ai_analyzer import OllamaError, analyze_with_ai, analyze_with_heuristics_only
from .config import get_settings
from .github_client import GitHubError
from .models import AnalyzeRequest, AnalyzeResponse, DemoSummary

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
        owner, repo, number = github_client.parse_pr_url(request.pr_url)
    except GitHubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        pr = await github_client.fetch_pull_request(owner, repo, number, token=settings.github_token)
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    heuristic_result = heuristics.analyze(pr)

    ai_enabled = True
    ai_error: str | None = None
    try:
        ai_result = await analyze_with_ai(pr, heuristic_result)
    except OllamaError as exc:
        logger.warning("Ollama analysis unavailable, falling back to heuristics only: %s", exc)
        ai_enabled = False
        ai_error = str(exc)
        ai_result = analyze_with_heuristics_only(pr, heuristic_result, reason=str(exc))
    except Exception as exc:  # noqa: BLE001 - any other unexpected failure also falls back
        logger.exception("Unexpected AI analysis failure, falling back to heuristics only")
        ai_enabled = False
        ai_error = f"Unexpected error calling Ollama: {exc}"
        ai_result = analyze_with_heuristics_only(pr, heuristic_result, reason=ai_error)

    return AnalyzeResponse(
        pr=pr,
        heuristics=heuristic_result,
        ai=ai_result,
        ai_enabled=ai_enabled,
        ai_error=ai_error,
        source="live",
    )
