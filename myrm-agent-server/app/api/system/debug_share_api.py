"""
[INPUT]: Diagnostic generation requests with raw logs, trace events, and user support notes.
[OUTPUT]: Physical-grade sanitized debug dumps, SHA256 checksums, and ephemeral share link contracts.
[POS]: myrm-agent/myrm-agent-server/app/api/system/debug_share_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.sanitized_debug_dump import (
    EphemeralShareLink,
    RedactionAuditRecord,
    SanitizedDebugDump,
    SanitizedDebugPackager,
)

router = APIRouter(tags=["debug-share"])

_packager = SanitizedDebugPackager(share_ttl_hours=48, max_views_before_burn=3)


class CreateDumpRequest(BaseModel):
    raw_logs: List[str] = Field(default_factory=list)
    recent_traces: Optional[List[Dict[str, str]]] = None
    user_note: str = ""


class CreateEphemeralLinkRequest(BaseModel):
    dump_id: str
    base_url: Optional[str] = None


class RedactionAuditSchema(BaseModel):
    rule_type: str
    masked_placeholder: str
    occurrences_count: int


class SystemVitalsSchema(BaseModel):
    os_name: str
    python_version: str
    cpu_cores: int
    memory_total_gb: float
    network_connectivity: str
    timestamp: str


class SanitizedDebugDumpResponse(BaseModel):
    dump_id: str
    vitals: SystemVitalsSchema
    sanitized_logs: List[str]
    recent_traces: List[Dict[str, str]]
    redacted_audits: List[RedactionAuditSchema]
    total_redacted_count: int
    user_note: str
    checksum_sha256: str
    created_at: str


class EphemeralShareLinkResponse(BaseModel):
    share_token: str
    dump_id: str
    share_url: str
    expires_at: str
    max_views: int
    remaining_views: int
    is_destroyed: bool
    created_at: str


class ConsumeShareResponse(BaseModel):
    dump: Optional[SanitizedDebugDumpResponse] = None
    remaining_views: int
    is_destroyed: bool
    error: Optional[str] = None


def _convert_dump_to_response(d: SanitizedDebugDump) -> SanitizedDebugDumpResponse:
    return SanitizedDebugDumpResponse(
        dump_id=d.dump_id,
        vitals=SystemVitalsSchema(
            os_name=d.vitals.os_name,
            python_version=d.vitals.python_version,
            cpu_cores=d.vitals.cpu_cores,
            memory_total_gb=d.vitals.memory_total_gb,
            network_connectivity=d.vitals.network_connectivity,
            timestamp=d.vitals.timestamp,
        ),
        sanitized_logs=d.sanitized_logs,
        recent_traces=d.recent_traces,
        redacted_audits=[
            RedactionAuditSchema(
                rule_type=a.rule_type.value if hasattr(a.rule_type, "value") else str(a.rule_type),
                masked_placeholder=a.masked_placeholder,
                occurrences_count=a.occurrences_count,
            )
            for a in d.redacted_audits
        ],
        total_redacted_count=d.total_redacted_count,
        user_note=d.user_note,
        checksum_sha256=d.checksum_sha256,
        created_at=d.created_at,
    )


@router.post(
    "/debug-share/dump",
    response_model=SanitizedDebugDumpResponse,
    status_code=status.HTTP_200_OK,
)
async def create_sanitized_dump(req: CreateDumpRequest) -> SanitizedDebugDumpResponse:
    """Generates a zero-leak physical-grade sanitized debug dump from client logs and traces."""
    dump = _packager.create_sanitized_dump(
        raw_logs=req.raw_logs,
        recent_traces=req.recent_traces,
        user_note=req.user_note,
    )
    return _convert_dump_to_response(dump)


@router.get(
    "/debug-share/dump/{dump_id}",
    response_model=SanitizedDebugDumpResponse,
    status_code=status.HTTP_200_OK,
)
async def get_sanitized_dump(
    dump_id: str = Path(..., description="Target debug dump identifier"),
) -> SanitizedDebugDumpResponse:
    """Retrieves an existing sanitized diagnostic dump."""
    dump = _packager.get_dump(dump_id)
    if not dump:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnostic dump {dump_id} not found",
        )
    return _convert_dump_to_response(dump)


@router.post(
    "/debug-share/ephemeral-link",
    response_model=EphemeralShareLinkResponse,
    status_code=status.HTTP_200_OK,
)
async def create_ephemeral_share_link(
    req: CreateEphemeralLinkRequest,
) -> EphemeralShareLinkResponse:
    """Creates a 48h ephemeral self-destructing share link with a 3-view burn quota."""
    base_url = req.base_url or "https://debug.myrm.ai/share"
    try:
        link = _packager.create_ephemeral_link(dump_id=req.dump_id, base_url=base_url)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dump {req.dump_id} not found",
        )

    return EphemeralShareLinkResponse(
        share_token=link.share_token,
        dump_id=link.dump_id,
        share_url=link.share_url,
        expires_at=link.expires_at,
        max_views=link.max_views,
        remaining_views=link.remaining_views,
        is_destroyed=link.is_destroyed,
        created_at=link.created_at,
    )


@router.get(
    "/debug-share/view/{share_token}",
    response_model=ConsumeShareResponse,
    status_code=status.HTTP_200_OK,
)
async def consume_ephemeral_share(
    share_token: str = Path(..., description="Secret ephemeral share token"),
) -> ConsumeShareResponse:
    """Consumes one view on an ephemeral share link and enforces self-destruction after 3 views."""
    dump, err = _packager.consume_ephemeral_link(share_token)
    if err:
        return ConsumeShareResponse(
            dump=None,
            remaining_views=0,
            is_destroyed=True,
            error=err,
        )

    link = _packager._ephemeral_links.get(share_token)
    rem = link.remaining_views if link else 0
    destroyed = link.is_destroyed if link else True

    return ConsumeShareResponse(
        dump=_convert_dump_to_response(dump) if dump else None,
        remaining_views=rem,
        is_destroyed=destroyed,
        error=None,
    )
