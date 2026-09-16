"""Analytics endpoints consumed by the RootIQ dashboards."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.services import analytics as analytics_service

router = APIRouter(prefix="/api/ai", tags=["Analytics"])


class RootCauseDistributionItem(BaseModel):
    root_cause: str
    exception_count: int


@router.get("/analytics/root-causes", response_model=list[RootCauseDistributionItem])
async def analytics_root_causes() -> list[RootCauseDistributionItem]:
    try:
        rows = await run_in_threadpool(analytics_service.get_root_cause_distribution)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load root cause distribution: {exc}") from exc

    return [RootCauseDistributionItem(**row) for row in rows]
