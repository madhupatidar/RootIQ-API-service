"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import database as db
from app.config import (
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_ORIGIN_REGEX,
    CORS_ALLOW_ORIGINS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)
from app.routers.analytics import router as analytics_router
from app.routers.exception_analysis import router as exception_analysis_router
from app.routers.upload import router as upload_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RootIQ - AI-Powered Exception Root Cause & Prevention Platform",
    description="APIs for exception ingestion, AI root cause analysis, and prevention insights.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api/upload")
app.include_router(exception_analysis_router, prefix="/api/analyze")
app.include_router(analytics_router)


@app.on_event("startup")
async def startup():
    """Apply the database schema on startup."""
    logger.info("Config: OLLAMA_BASE_URL=%s OLLAMA_MODEL=%s", OLLAMA_BASE_URL, OLLAMA_MODEL)
    logger.info("Running database schema migration …")
    try:
        db.run_schema()
        logger.info("Database schema ready.")
    except Exception:
        logger.exception("Failed to initialise database – check DATABASE_URL and PostgreSQL connection.")
        raise


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
