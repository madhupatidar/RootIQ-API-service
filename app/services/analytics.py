"""Analytics queries backing the RootIQ dashboards."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.database import SessionLocal

_ROOT_CAUSE_DISTRIBUTION_SQL = text(
    """
    SELECT COALESCE(root_cause, 'Uncategorized') AS root_cause,
           COUNT(*) AS exception_count
    FROM ai_analysis_results
    GROUP BY COALESCE(root_cause, 'Uncategorized')
    ORDER BY exception_count DESC
    LIMIT :limit
    """
)


def get_root_cause_distribution(limit: int = 12) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.execute(_ROOT_CAUSE_DISTRIBUTION_SQL, {"limit": int(limit)}).mappings().all()
    return [dict(row) for row in rows]
