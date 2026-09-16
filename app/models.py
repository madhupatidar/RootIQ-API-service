"""Shared pydantic models for exception ingestion."""

from __future__ import annotations

from pydantic import BaseModel


class ExceptionInput(BaseModel):
    """Normalized exception payload produced by the CSV/Excel mappers."""

    # Identity
    osdType: str = ""
    osdNumber: str = ""
    proNumber: str = ""

    # Time / ownership
    entryBy: str = ""
    createdDate: str = ""
    lastUpdatedDate: str = ""

    # Investigation
    investigationStatus: str = ""
    remarks: str = ""

    # Quantitative attributes (kept as text to match raw CSV values)
    totalValue: str = "0"
    value1k: str = "0"
    totalPieces: str = "0"
    pieces: str = "0"
    weight: str = "0"
    numberOfPallets: str = "0"
    handlingUnits: str = "0"
