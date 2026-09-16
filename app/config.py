"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# ── Paths ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = BASE_DIR / "sql"

# ── PostgreSQL ───────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/rootiq",
)

# ── Ollama (the only supported LLM provider) ────────────────
# Ollama Cloud requires OLLAMA_API_KEY. For a local daemon set
# OLLAMA_BASE_URL=http://localhost:11434.
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")
OLLAMA_API_KEY: str = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")

# httpx has multiple timeout phases; keep connect small but allow long reads.
OLLAMA_CONNECT_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "10"))
OLLAMA_READ_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_READ_TIMEOUT_SECONDS", "240"))
OLLAMA_WRITE_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_WRITE_TIMEOUT_SECONDS", "30"))
OLLAMA_POOL_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_POOL_TIMEOUT_SECONDS", "30"))

# ── CORS (dev / front-end integration) ─────────────────────
# A React/Vite dev server sends `Origin: http://localhost:5173` even when the
# API is remote. The default regex allows any localhost port.
CORS_ALLOW_ORIGINS: list[str] = _env_csv("CORS_ALLOW_ORIGINS", "")
CORS_ALLOW_ORIGIN_REGEX: str | None = os.getenv(
    "CORS_ALLOW_ORIGIN_REGEX",
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
).strip() or None

# Only enable when intentionally using cookies/HTTP auth.
# When true, '*' must not be used as an allowed origin.
CORS_ALLOW_CREDENTIALS: bool = _env_bool("CORS_ALLOW_CREDENTIALS", False)
