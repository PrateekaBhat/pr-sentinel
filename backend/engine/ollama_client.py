from __future__ import annotations

import json
import re

import httpx

from .config import get_settings


class OllamaError(Exception):
    """Raised when Ollama can't be reached or returns an unusable response."""


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


async def chat_json(system: str, user: str, timeout: float = 300.0) -> dict:
    """Send a chat completion request to Ollama and parse a JSON object back."""
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=timeout) as client:
            resp = await client.post("/api/chat", json=payload)
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Couldn't reach Ollama at {settings.ollama_base_url}. "
            "Is it running? Try `ollama serve` in another terminal."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError(
            f"Ollama timed out after {timeout:.0f}s. Local CPU inference may exceed the "
            "configured analysis budget for this PR. The deterministic policy result "
            "remains authoritative."
        ) from exc

    if resp.status_code == 404:
        raise OllamaError(
            f"Model '{settings.ollama_model}' isn't pulled yet. Run: "
            f"`ollama pull {settings.ollama_model}`"
        )
    if resp.status_code >= 400:
        raise OllamaError(f"Ollama error ({resp.status_code}): {resp.text[:300]}")

    body = resp.json()
    text = body.get("message", {}).get("content", "")
    if not text:
        raise OllamaError("Ollama returned an empty response.")

    try:
        return extract_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise OllamaError(
            "Model output wasn't valid JSON. Local models occasionally drift from the "
            "requested format — retrying, or using a larger model, usually helps."
        ) from exc


async def embed(text: str, timeout: float = 60.0) -> list[float]:
    """Embed a single string via Ollama's embeddings endpoint."""
    settings = get_settings()
    payload = {"model": settings.ollama_embed_model, "prompt": text[:8000]}

    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=timeout) as client:
            resp = await client.post("/api/embeddings", json=payload)
    except httpx.ConnectError as exc:
        raise OllamaError(f"Couldn't reach Ollama at {settings.ollama_base_url} for embeddings.") from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("Ollama embedding request timed out.") from exc

    if resp.status_code == 404:
        raise OllamaError(
            f"Embedding model '{settings.ollama_embed_model}' isn't pulled yet. Run: "
            f"`ollama pull {settings.ollama_embed_model}`"
        )
    if resp.status_code >= 400:
        raise OllamaError(f"Ollama embeddings error ({resp.status_code}): {resp.text[:300]}")

    vector = resp.json().get("embedding")
    if not vector:
        raise OllamaError("Ollama returned an empty embedding.")
    return vector
