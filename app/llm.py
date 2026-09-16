"""Ollama chat helper returning structured JSON responses."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import (
    OLLAMA_API_KEY,
    OLLAMA_BASE_URL,
    OLLAMA_CONNECT_TIMEOUT_SECONDS,
    OLLAMA_MODEL,
    OLLAMA_POOL_TIMEOUT_SECONDS,
    OLLAMA_READ_TIMEOUT_SECONDS,
    OLLAMA_WRITE_TIMEOUT_SECONDS,
)


def _ollama_chat(messages: list[dict[str, str]], model: str) -> str:
    base_url = OLLAMA_BASE_URL.rstrip("/")
    timeout = httpx.Timeout(
        connect=OLLAMA_CONNECT_TIMEOUT_SECONDS,
        read=OLLAMA_READ_TIMEOUT_SECONDS,
        write=OLLAMA_WRITE_TIMEOUT_SECONDS,
        pool=OLLAMA_POOL_TIMEOUT_SECONDS,
    )
    request_payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    headers: dict[str, str] = {}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    response = httpx.post(
        f"{base_url}/api/chat",
        json=request_payload,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty response")
    return content


def call_llm(messages: list[dict[str, str]], model: str | None = None) -> dict[str, Any]:
    """Call Ollama and return its JSON-object response."""
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list of chat message objects")

    selected_model = (model or OLLAMA_MODEL).strip()
    if not selected_model:
        raise RuntimeError("OLLAMA_MODEL is not configured")

    try:
        content = _ollama_chat(messages, selected_model)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama API request failed: {exc}") from exc

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama response was not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Ollama response is not a JSON object")
    return payload
