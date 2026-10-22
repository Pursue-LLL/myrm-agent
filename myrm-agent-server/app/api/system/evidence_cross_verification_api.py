"""
[INPUT]: Multi-source evidence records, error code context, and root cause diagnosis requests.
[OUTPUT]: Pydantic schemas and REST endpoints for multi-source evidence cross-verification and 4-tier confidence scoring.
[POS]: myrm-agent/myrm-agent-server/app/api/system/evidence_cross_verification_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.evidence_cross_verification import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceSourceType,
    VerificationDiagnosisRequest,
    VerificationFinding,
    get_default_evidence_verifier,
)

router = APIRouter(prefix="/evidence-verification", tags=["evidence-verification"])


# --- Pydantic Request & Response Schemas ---


class RecordEvidenceItemRequest(BaseModel):
    source_type: str = Field(
        ...,
        description="KNOWLEDGE_BASE, CODE_SYMBOL, SOURCE_LOGIC, or RUNTIME_TELEMETRY",
    )
    title: str = Field(..., description="Short identifier of the proof or fact")
    detail: str = Field(..., description="Detailed content of the proof")
    is_verified: bool = Field(default=True, description="Whether the evidence is confirmed")
    file_path: str = Field(default="", description="Relevant source code path if applicable")
    line_number: int = Field(default=0, ge=0, description="Relevant line number if applicable")
    trace_id: str = Field(default="", description="Distributed trace span id if applicable")


class DiagnoseRootCauseRequest(BaseModel):
    error_code: str = Field(..., description="Error code or exception class")
    event_date: str = Field(..., description="Occurrence date in YYYY-MM-DD to avoid trace pollution")
    caller_trace_id: str = Field(..., description="Trace span ID of the failing request")
    raw_symptom: str = Field(..., description="Raw symptom or failure summary")
    kb_doc_hint: str = Field(default="", description="Optional knowledge base or runbook reference")
    code_def_hint: str = Field(default="", description="Optional constant or enum definition in code")
    call_budget: int = Field(default=15, ge=1, le=15, description="Search call budget cap")


class EvidenceItemModel(BaseModel):
    source_type: str
    title: str
    detail: str
    is_verified: bool
    timestamp_ms: int
    weight: float
    file_path: str
    line_number: int
    trace_id: str


class VerificationFindingResponse(BaseModel):
    diagnosis_id: str
    error_code: str
    resolved_code_meaning: str
    target_file_path: str
    target_line_number: int
    root_cause_category: str
    explanation: str
    recommended_patch: str
    confidence_score: int
    confidence_level: str
    evidences: List[EvidenceItemModel]
    bilateral_verified: bool
    created_at_ms: int


# --- Helper Converters ---


def _to_evidence_model(item: EvidenceItem) -> EvidenceItemModel:
    return EvidenceItemModel(
        source_type=item.source_type.value,
        title=item.title,
        detail=item.detail,
        is_verified=item.is_verified,
        timestamp_ms=item.timestamp_ms,
        weight=item.weight,
        file_path=item.file_path,
        line_number=item.line_number,
        trace_id=item.trace_id,
    )


def _to_finding_response(finding: VerificationFinding) -> VerificationFindingResponse:
    return VerificationFindingResponse(
        diagnosis_id=finding.diagnosis_id,
        error_code=finding.error_code,
        resolved_code_meaning=finding.resolved_code_meaning,
        target_file_path=finding.target_file_path,
        target_line_number=finding.target_line_number,
        root_cause_category=finding.root_cause_category,
        explanation=finding.explanation,
        recommended_patch=finding.recommended_patch,
        confidence_score=finding.confidence_score,
        confidence_level=finding.confidence_level.value,
        evidences=[_to_evidence_model(e) for e in finding.evidences],
        bilateral_verified=finding.bilateral_verified,
        created_at_ms=finding.created_at_ms,
    )


# --- Endpoints ---


@router.post("/record-evidence")
async def record_evidence(req: RecordEvidenceItemRequest) -> Dict[str, bool]:
    """Record an individual investigative evidence item into the verification engine."""
    engine = get_default_evidence_verifier()
    try:
        resolved_type = EvidenceSourceType(req.source_type.upper())
    except ValueError:
        resolved_type = EvidenceSourceType.RUNTIME_TELEMETRY

    evidence = EvidenceItem(
        source_type=resolved_type,
        title=req.title,
        detail=req.detail,
        is_verified=req.is_verified,
        file_path=req.file_path,
        line_number=req.line_number,
        trace_id=req.trace_id,
    )
    engine.record_evidence(evidence)
    return {"ok": True}


@router.post("/diagnose", response_model=VerificationFindingResponse)
async def diagnose_root_cause(
    req: DiagnoseRootCauseRequest,
) -> VerificationFindingResponse:
    """Execute action-oriented root cause cross-verification and produce 4-tier confidence findings."""
    engine = get_default_evidence_verifier()
    diagnosis_req = VerificationDiagnosisRequest(
        error_code=req.error_code,
        event_date=req.event_date,
        caller_trace_id=req.caller_trace_id,
        raw_symptom=req.raw_symptom,
        kb_doc_hint=req.kb_doc_hint,
        code_def_hint=req.code_def_hint,
        call_budget=req.call_budget,
    )
    finding = engine.diagnose_root_cause(req=diagnosis_req)
    return _to_finding_response(finding)


@router.get("/recent-diagnoses", response_model=List[VerificationFindingResponse])
async def get_recent_diagnoses(
    limit: int = Query(20, ge=1, le=100, description="Maximum items to return"),
) -> List[VerificationFindingResponse]:
    """Retrieve historical root cause diagnoses and confidence breakdowns."""
    engine = get_default_evidence_verifier()
    findings = engine.get_recent_diagnoses(limit=limit)
    return [_to_finding_response(f) for f in findings]


@router.post("/reset")
async def reset_verification_engine() -> Dict[str, bool]:
    """Reset all active collected evidences and diagnostic history."""
    engine = get_default_evidence_verifier()
    engine.reset()
    return {"ok": True}
