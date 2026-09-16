"""AI exception analysis endpoints (batch analysis, history, retention cleanup)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.config import OLLAMA_MODEL
from app.database import SessionLocal
from app.llm import call_llm

router = APIRouter(tags=["Exception Analysis"])

ROOT_CAUSE_TAXONOMY = [
    "Improper Packaging",
    "Missed Scan",
    "Misrouting",
    "Handling Damage",
    "Documentation Errors",
    "Consignee Issue",
    "Carrier Error",
    "Labeling Error",
    "Other",
]

CONFIDENCE_LEVELS = ["High", "Medium", "Low"]

SYSTEM_PROMPT = """You are an expert freight operations analyst for SAIA LTL.
You analyze OS&D (Overage, Shortage, Refusal/Damage, On-Hand Delivery, Misdelivery) exception
investigation records to determine the most likely ROOT CAUSE and recommend a PREVENTIVE ACTION.

Each input record represents ONE exception and contains:
- exception_number, exception_type, pro_number
- a set of investigation Q&A checks (OD400, BL, DR, PS, Consignee, Shipment) with Yes/No answers
  and free-text responses from the investigator
- error_message: system-generated investigation status message
- clearing_code: the official disposition code recorded for this exception
- clearing_code description: the plain-English meaning on file for that code

Your task:
1. Determine the root cause of the exception using the investigation Q&A and error_message as
   primary evidence. Quote the specific Q&A answer(s) that justify your conclusion.
2. Use the clearing code and its description as supporting disposition context, never as the
   only deciding factor.
3. Recommend specific, actionable preventive measures tied to the root cause (process, training,
   scan/audit, or system control - not generic advice).
4. Report confidence based on how complete and consistent the investigation evidence is.

Respond ONLY in valid JSON. No markdown. No preamble. No explanation outside JSON.
"""


class InvestigationQAInput(BaseModel):
    check_code: str
    check_label: str
    answer: str | None = None
    response_text: str | None = None


class ExceptionAnalysisRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pronumber: str | None = None
    exception_number: str | None = Field(default=None, alias="exceptionNumber")
    type_code: str = Field(..., min_length=1)
    exception_category: str = Field(..., min_length=1)
    entry_user: str | None = None
    error_message: str | None = None
    investigation_status: str | None = None
    clearing_code: str | None = None
    clearing_code_full_form: str | None = Field(default=None, alias="clearingCodeFullForm")
    investigation_qa: list[InvestigationQAInput] = Field(default_factory=list)


class KeySignal(BaseModel):
    check_code: str
    answer: str
    signal: str


class ExceptionAnalysisResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pronumber: str
    exception_number: str | None = Field(default=None, alias="exceptionNumber")
    type_code: str
    exception_category: str
    root_cause: str
    root_cause_summary: str = Field(default="", alias="rootCauseSummary")
    supporting_evidence: list[str] = Field(default_factory=list, alias="supportingEvidence")
    key_signals: list[KeySignal] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"]
    reasoning: str
    analysis: str = ""
    prevention_recommendations: list[str] = Field(default_factory=list)
    analyzed_at: datetime
    model_used: str


class BatchRequest(BaseModel):
    records: list[ExceptionAnalysisRequest] = Field(default_factory=list)


class BatchError(BaseModel):
    pronumber: str
    error: str


class BatchResponse(BaseModel):
    results: list[ExceptionAnalysisResponse] = Field(default_factory=list)
    errors: list[BatchError] = Field(default_factory=list)
    total: int
    succeeded: int


class ClearDataRequest(BaseModel):
    """Request to clear old analysis records."""

    days_old: int = 30
    root_cause: str | None = None
    type_code: str | None = None


class ClearDataResponse(BaseModel):
    deleted_count: int
    message: str


def _normalize_answer(answer: str | None) -> str:
    if answer is None:
        return "NOT CHECKED"

    normalized = answer.strip().upper()
    if normalized == "Y":
        return "YES"
    if normalized == "N":
        return "NO"
    return normalized or "NOT CHECKED"


def _build_user_prompt(record: ExceptionAnalysisRequest) -> str:
    checklist_lines: list[str] = []
    for qa in record.investigation_qa:
        answer_label = _normalize_answer(qa.answer)
        response_text = (qa.response_text or "No notes provided").strip() or "No notes provided"
        checklist_lines.append(f'- {qa.check_label}: {answer_label} - "{response_text}"')

    checklist_block = "\n".join(checklist_lines) if checklist_lines else "- No checklist responses provided"

    return (
        f"Exception Number (primary identifier): {(record.exception_number or '').strip() or 'Unknown'}\n"
        f"Pro Number (reference only): {(record.pronumber or '').strip() or 'Unknown'}\n"
        f"Exception Type: {record.type_code} ({record.exception_category})\n"
        f"Entry User: {(record.entry_user or '').strip() or 'Not provided'}\n"
        f"Error Message: {(record.error_message or '').strip() or 'Not provided'}\n"
        f"Investigation Status: {(record.investigation_status or '').strip() or 'Not provided'}\n"
        f"Clearing Code: {(record.clearing_code or '').strip() or 'Not provided'}\n"
        f"Clearing Code Description: {(record.clearing_code_full_form or '').strip() or 'Not provided'}\n\n"
        "Investigation Checklist:\n"
        f"{checklist_block}\n\n"
        "Classify this exception using all evidence. Use clearing code + clearing code full description as supportive disposition context.\n"
        "Use clearing code full description to improve root-cause precision and prevention recommendations for similar future exceptions.\n"
        "If checklist and clearing code conflict, explain discrepancy and provide the most likely root cause.\n"
        "Return ONLY this JSON:\n"
        "{\n"
        '  "exceptionNumber": str,\n'
        '  "root_cause": one of ["Improper Packaging", "Missed Scan", "Misrouting",\n'
        '                        "Handling Damage", "Documentation Errors",\n'
        '                        "Consignee Issue", "Carrier Error",\n'
        '                        "Labeling Error", "Other"],\n'
        '  "rootCauseSummary": "1 concise sentence naming the final likely root cause",\n'
        '  "supportingEvidence": ["evidence item 1", "evidence item 2", "evidence item 3"],\n'
        '  "key_signals": [\n'
        '    { "check_code": str, "answer": str, "signal": "why this check matters" }\n'
        "  ],\n"
        '  "confidence": "High" | "Medium" | "Low",\n'
        '  "analysis": "2-4 sentences explaining how checklist + error/status + clearing code led to conclusion",\n'
        '  "reasoning": "2-4 sentences citing specific checklist answers and clearing signals",\n'
        '  "prevention_recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]\n'
        "}\n\n"
        "Confidence rules:\n"
        "- High: clearing code/description and checklist strongly align\n"
        "- Medium: evidence is mixed but one cause is still more likely\n"
        "- Low: contradictory or sparse evidence"
    )


def _as_string_list(raw_value: Any) -> list[str]:
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str) and raw_value.strip():
        return [raw_value.strip()]
    return []


def _parse_key_signals(raw_value: Any) -> list[KeySignal]:
    key_signals: list[KeySignal] = []
    if not isinstance(raw_value, list):
        return key_signals

    for item in raw_value:
        if not isinstance(item, dict):
            continue
        check_code = str(item.get("check_code") or "").strip()
        answer = str(item.get("answer") or "").strip()
        signal = str(item.get("signal") or "").strip()
        if check_code and signal:
            key_signals.append(KeySignal(check_code=check_code, answer=answer, signal=signal))

    return key_signals


def _normalize_result(payload: dict[str, Any]) -> dict[str, Any]:
    root_cause = str(payload.get("root_cause") or "Other").strip()
    if root_cause not in ROOT_CAUSE_TAXONOMY:
        root_cause = "Other"

    root_cause_summary = str(
        payload.get("rootCauseSummary")
        or payload.get("root_cause_summary")
        or f"Most likely root cause: {root_cause}."
    ).strip() or f"Most likely root cause: {root_cause}."

    supporting_evidence = _as_string_list(
        payload.get("supportingEvidence") or payload.get("supporting_evidence")
    ) or ["Model did not return structured supporting evidence."]

    confidence = str(payload.get("confidence") or "Medium").strip().title()
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "Medium"

    analysis = str(payload.get("analysis") or payload.get("reasoning") or "").strip() or "No analysis provided by model."
    reasoning = str(payload.get("reasoning") or "").strip() or "No reasoning provided by model."

    recommendations = _as_string_list(payload.get("prevention_recommendations")) or [
        "Review checklist execution and reinforce SOP compliance."
    ]

    return {
        "root_cause": root_cause,
        "root_cause_summary": root_cause_summary,
        "supporting_evidence": supporting_evidence,
        "key_signals": _parse_key_signals(payload.get("key_signals")),
        "confidence": confidence,
        "analysis": analysis,
        "reasoning": reasoning,
        "prevention_recommendations": recommendations,
    }


def _save_analysis(record: ExceptionAnalysisResponse) -> None:
    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO ai_analysis_results (
                    pronumber,
                    exception_number,
                    type_code,
                    exception_category,
                    root_cause,
                    root_cause_summary,
                    confidence,
                    reasoning,
                    analysis,
                    supporting_evidence,
                    prevention_recommendations,
                    key_signals,
                    analyzed_at,
                    model_used,
                    created_at
                ) VALUES (
                    :pronumber,
                    :exception_number,
                    :type_code,
                    :exception_category,
                    :root_cause,
                    :root_cause_summary,
                    :confidence,
                    :reasoning,
                    :analysis,
                    CAST(:supporting_evidence AS JSONB),
                    CAST(:prevention_recommendations AS JSONB),
                    CAST(:key_signals AS JSONB),
                    :analyzed_at,
                    :model_used,
                    :created_at
                )
                """
            ),
            {
                "pronumber": record.pronumber,
                "exception_number": record.exception_number,
                "type_code": record.type_code,
                "exception_category": record.exception_category,
                "root_cause": record.root_cause,
                "root_cause_summary": record.root_cause_summary,
                "confidence": record.confidence,
                "reasoning": record.reasoning,
                "analysis": record.analysis,
                "supporting_evidence": json.dumps(record.supporting_evidence),
                "prevention_recommendations": json.dumps(record.prevention_recommendations),
                "key_signals": json.dumps([item.model_dump() for item in record.key_signals]),
                "analyzed_at": record.analyzed_at,
                "model_used": record.model_used,
                "created_at": datetime.utcnow(),
            },
        )
        session.commit()


async def _analyze_single_record(record: ExceptionAnalysisRequest, model: str) -> ExceptionAnalysisResponse:
    identifier = (record.exception_number or "").strip() or (record.pronumber or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Either exception_number or pronumber is required.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(record)},
    ]

    payload = await run_in_threadpool(call_llm, messages, model)
    normalized = _normalize_result(payload)

    response = ExceptionAnalysisResponse(
        pronumber=(record.pronumber or "").strip() or identifier,
        exception_number=(record.exception_number or "").strip() or None,
        type_code=record.type_code,
        exception_category=record.exception_category,
        analyzed_at=datetime.utcnow(),
        model_used=model,
        **normalized,
    )

    try:
        await run_in_threadpool(_save_analysis, response)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to persist analysis result: {exc}") from exc

    return response


@router.post("/batch", response_model=BatchResponse)
async def analyze_batch(request: BatchRequest) -> BatchResponse:
    model = OLLAMA_MODEL
    results: list[ExceptionAnalysisResponse] = []
    errors: list[BatchError] = []

    for record in request.records:
        try:
            results.append(await _analyze_single_record(record, model))
        except Exception as exc:
            identifier = (record.exception_number or "").strip() or (record.pronumber or "").strip() or "unknown"
            errors.append(BatchError(pronumber=identifier, error=str(exc)))

    return BatchResponse(
        results=results,
        errors=errors,
        total=len(request.records),
        succeeded=len(results),
    )


@router.get("/history", response_model=list[ExceptionAnalysisResponse])
async def analyze_history() -> list[ExceptionAnalysisResponse]:
    try:
        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT
                        pronumber,
                        exception_number,
                        type_code,
                        exception_category,
                        root_cause,
                        root_cause_summary,
                        analysis,
                        key_signals,
                        supporting_evidence,
                        confidence,
                        reasoning,
                        prevention_recommendations,
                        analyzed_at,
                        model_used
                    FROM ai_analysis_results
                    ORDER BY analyzed_at DESC
                    LIMIT 500
                    """
                )
            ).mappings().all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load analysis history: {exc}") from exc

    history: list[ExceptionAnalysisResponse] = []
    for row in rows:
        analyzed_at = row.get("analyzed_at")
        if not isinstance(analyzed_at, datetime):
            analyzed_at = datetime.utcnow()

        root_cause = str(row.get("root_cause") or "Other")
        history.append(
            ExceptionAnalysisResponse(
                pronumber=str(row.get("pronumber") or ""),
                exception_number=row.get("exception_number"),
                type_code=str(row.get("type_code") or ""),
                exception_category=str(row.get("exception_category") or ""),
                root_cause=root_cause,
                root_cause_summary=str(row.get("root_cause_summary") or f"Most likely root cause: {root_cause}."),
                supporting_evidence=_as_string_list(row.get("supporting_evidence")),
                key_signals=_parse_key_signals(row.get("key_signals")),
                confidence=str(row.get("confidence") or "Medium").title(),
                analysis=str(row.get("analysis") or ""),
                reasoning=str(row.get("reasoning") or "No reasoning available."),
                prevention_recommendations=_as_string_list(row.get("prevention_recommendations")),
                analyzed_at=analyzed_at,
                model_used=str(row.get("model_used") or OLLAMA_MODEL),
            )
        )

    return history


@router.delete("/clear", response_model=ClearDataResponse)
async def clear_old_data(request: ClearDataRequest) -> ClearDataResponse:
    """Delete analysis records older than the requested age, with optional filters."""
    if request.days_old < 1:
        raise HTTPException(status_code=400, detail="days_old must be at least 1")

    conditions = ["created_at < NOW() - make_interval(days => :days_old)"]
    params: dict[str, Any] = {"days_old": request.days_old}

    if request.root_cause:
        conditions.append("root_cause = :root_cause")
        params["root_cause"] = request.root_cause

    if request.type_code:
        conditions.append("type_code = :type_code")
        params["type_code"] = request.type_code

    query = f"DELETE FROM ai_analysis_results WHERE {' AND '.join(conditions)}"

    try:
        with SessionLocal() as session:
            result = session.execute(text(query), params)
            deleted_count = result.rowcount
            session.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear data: {exc}") from exc

    return ClearDataResponse(
        deleted_count=deleted_count,
        message=f"Successfully deleted {deleted_count} analysis records older than {request.days_old} days.",
    )
