"""File upload endpoints for exception ingestion (POC: OV only)."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.csv_mapper import KNOWN_TYPES, SUPPORTED_TYPES, TYPE_REGISTRY

router = APIRouter(tags=["Upload"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
BASE_REQUIRED_COLUMNS = ["TYPE", "PRONUMBER", "ENTRYUSER", "ENTRYSTATUS"]

COLUMN_ALIASES: dict[str, str] = {
    "EXCEPTION TYPE": "TYPE",
    "PRO NUMBER": "PRONUMBER",
    "ENTRY USER": "ENTRYUSER",
    "ENTRY STATUS": "ENTRYSTATUS",
    "INVESTIGATION STATUS": "INVESTIGATION_STATUS",
    "ERROR MESSAGE": "ERROR_MESSAGE",
    "EXCEPTION NUMBER": "EXCEPTION_NUMBER",
    "CLEARING CODE": "CLEARING_CODE",
    "CLEARING CODE FULL FORM": "CLEARING_CODE_FULL_FORM",
    "CLEARING CODE DESCRIPTION (FULL FORM)": "CLEARING_CODE_FULL_FORM",
    "OD400 CHECK": "OD400_CHK",
    "OD400 CHECK RESPONSE": "OD400_CHK_RESP",
    "BL CHECK": "BL_CHK",
    "BL CHECK RESPONSE": "BL_CHK_RESP",
    "DR CHECK": "DR_CHK",
    "DR CHECK RESPONSE": "DR_CHK_RESP",
    "PS CHECK": "PS_CHK",
    "PS CHECK RESPONSE": "PS_CHK_RESP",
    "CONSIGNEE CHECK": "CONSIGNEE_CHK",
    "CONSIGNEE CHECK RESPONSE": "CONSIGNEE_CHK_RESP",
    "SHIPMENT CHECK": "SHIPMENTCHK",
    "SHIPMENT CHECK RESPONSE": "SHIPMENTCHK_RESP",
}


class InvestigationQA(BaseModel):
    check_code: str
    check_label: str
    answer: str | None = None
    response_text: str | None = None


class ParsedExceptionRecord(BaseModel):
    pronumber: str
    exception_number: str | None = None
    type_code: str
    exception_category: str
    entry_user: str
    entry_status: str
    date_added: str | None = None
    error_message: str | None = None
    investigation_status: str | None = None
    clearing_code: str | None = None
    clearing_code_full_form: str | None = None
    investigation_qa: list[InvestigationQA] = Field(default_factory=list)


class UploadSummary(BaseModel):
    type_detected: str
    exception_category: str
    total_rows: int
    complete_rows: int
    skipped_rows: int
    skip_reasons: dict[str, int]


class UploadResponse(UploadSummary):
    records: list[ParsedExceptionRecord] = Field(default_factory=list)


def _read_dataframe(file_name: str, raw_bytes: bytes) -> pd.DataFrame:
    file_ext = Path(file_name).suffix.lower()
    source = BytesIO(raw_bytes)

    try:
        if file_ext == ".csv":
            return pd.read_csv(source)
        if file_ext == ".xlsx":
            return pd.read_excel(source, engine="openpyxl")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to parse file content: {exc}") from exc

    raise HTTPException(status_code=400, detail="Unsupported file type. Please upload .csv or .xlsx")


def _normalize_cell(value: Any) -> Any:
    if pd.isna(value):
        return None

    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed or trimmed == "----":
            return None
        return trimmed

    return value


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(col).strip().upper() for col in normalized.columns]

    for source_column, target_column in COLUMN_ALIASES.items():
        if source_column in normalized.columns:
            if target_column not in normalized.columns:
                normalized[target_column] = normalized[source_column]
            normalized = normalized.drop(columns=[source_column])

    if "ENTRYSTATUS" not in normalized.columns and "INVESTIGATION_STATUS" in normalized.columns:
        normalized["ENTRYSTATUS"] = normalized["INVESTIGATION_STATUS"]

    duplicate_columns = normalized.columns[normalized.columns.duplicated()].tolist()
    if duplicate_columns:
        duplicate_list = ", ".join(sorted(set(duplicate_columns)))
        raise HTTPException(status_code=400, detail=f"Duplicate columns after normalization: {duplicate_list}")

    for column in normalized.columns:
        normalized[column] = normalized[column].map(_normalize_cell)

    if "TYPE" in normalized.columns:
        normalized["TYPE"] = normalized["TYPE"].map(
            lambda value: value.upper() if isinstance(value, str) else value
        )

    for type_info in TYPE_REGISTRY.values():
        for check_column, _, _ in type_info.get("checks", []):
            if check_column in normalized.columns:
                normalized[check_column] = normalized[check_column].map(
                    lambda value: value.upper() if isinstance(value, str) else value
                )

    return normalized


def _validate_base_columns(df: pd.DataFrame) -> None:
    missing = [column for column in BASE_REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(missing)}")


def _detect_type(df: pd.DataFrame) -> str:
    for value in df["TYPE"].tolist():
        if value is None:
            continue
        candidate = str(value).strip().upper()
        if not candidate or candidate == "----":
            continue
        return candidate
    raise HTTPException(status_code=400, detail="Unable to detect exception type from TYPE column")


def _to_optional_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _to_iso_date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text_value = _to_optional_text(value)
    if not text_value:
        return None

    parsed = pd.to_datetime(text_value, errors="coerce")
    if pd.isna(parsed):
        return text_value
    return parsed.date().isoformat()


def _build_skip_reasons(df: pd.DataFrame, complete_mask: pd.Series) -> dict[str, int]:
    skipped_df = df[~complete_mask]
    reasons: dict[str, int] = {}

    for value in skipped_df["ENTRYSTATUS"].tolist():
        reason = _to_optional_text(value) or "Unknown"
        reasons[reason] = reasons.get(reason, 0) + 1

    return reasons


def _is_complete_status(value: Any) -> bool:
    text_value = _to_optional_text(value)
    if not text_value:
        return False

    normalized = text_value.strip().lower()
    return normalized in {"complete", "completed", "closed", "resolved", "11"}


@router.post("/exceptions", response_model=UploadResponse)
async def upload_exceptions(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file name in upload payload")

    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload .csv or .xlsx")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    dataframe = _read_dataframe(file.filename, raw_bytes)
    if dataframe.empty:
        raise HTTPException(status_code=400, detail="Uploaded file has no data rows")

    normalized_df = _normalize_dataframe(dataframe)
    _validate_base_columns(normalized_df)

    type_detected = _detect_type(normalized_df)
    if type_detected not in KNOWN_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown exception type: {type_detected}")

    if type_detected not in SUPPORTED_TYPES:
        supported = ", ".join(sorted(SUPPORTED_TYPES))
        raise HTTPException(
            status_code=400,
            detail=(
                f"Exception type {type_detected} is not supported in this version. "
                f"Supported types: {supported}. Additional types coming in Phase 2."
            ),
        )

    type_info = TYPE_REGISTRY[type_detected]
    checks: list[tuple[str, str, str]] = list(type_info.get("checks", []))
    expected_check_columns = [column for check in checks for column in check[:2]]
    missing_check_columns = [column for column in expected_check_columns if column not in normalized_df.columns]
    if missing_check_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing_check_columns)}",
        )

    total_rows = len(normalized_df.index)
    complete_mask = normalized_df["ENTRYSTATUS"].map(_is_complete_status)

    complete_df = normalized_df[complete_mask]
    complete_rows = len(complete_df.index)
    skipped_rows = total_rows - complete_rows
    skip_reasons = _build_skip_reasons(normalized_df, complete_mask)

    records: list[ParsedExceptionRecord] = []
    for _, row in complete_df.iterrows():
        investigation_qa = [
            InvestigationQA(
                check_code=check_column,
                check_label=check_label,
                answer=_to_optional_text(row.get(check_column)),
                response_text=_to_optional_text(row.get(response_column)),
            )
            for check_column, response_column, check_label in checks
        ]

        records.append(
            ParsedExceptionRecord(
                pronumber=_to_optional_text(row.get("PRONUMBER")) or "",
                exception_number=_to_optional_text(row.get("EXCEPTION_NUMBER")),
                type_code=type_detected,
                exception_category=str(type_info.get("category") or "Overage"),
                entry_user=_to_optional_text(row.get("ENTRYUSER")) or "",
                entry_status=_to_optional_text(row.get("ENTRYSTATUS")) or "",
                date_added=_to_iso_date(row.get("DATEADDED")),
                error_message=_to_optional_text(row.get("ERROR_MESSAGE")),
                investigation_status=_to_optional_text(row.get("INVESTIGATION_STATUS")),
                clearing_code=_to_optional_text(row.get("CLEARING_CODE")),
                clearing_code_full_form=_to_optional_text(row.get("CLEARING_CODE_FULL_FORM")),
                investigation_qa=investigation_qa,
            )
        )

    return UploadResponse(
        type_detected=type_detected,
        exception_category=str(type_info.get("category") or "Overage"),
        total_rows=total_rows,
        complete_rows=complete_rows,
        skipped_rows=skipped_rows,
        skip_reasons=skip_reasons,
        records=records,
    )
