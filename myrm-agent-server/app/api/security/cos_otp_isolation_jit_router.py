"""API router for CoS Sensitive OTP Isolation, Recovery Blackhole, and JIT Authorization Suite.

[POS] app/api/security/cos_otp_isolation_jit_router.py
[INPUT] app/schemas/cos_otp_isolation_jit.py, app/services/security/cos_otp_isolation_jit_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.cos_otp_isolation_jit import (
    BlackholeCheckRequest,
    BlackholeCheckResponse,
    ConsumeJitTicketRequest,
    ConsumeJitTicketResponse,
    EvaluateQuotaRequest,
    EvaluateQuotaResponse,
    InspectMessageOtpRequest,
    InspectMessageOtpResponse,
    IssueJitTicketRequest,
    JitTicketResponse,
)
from app.services.security.cos_otp_isolation_jit_service import (
    CosOtpIsolationJitService,
    get_cos_otp_isolation_jit_service,
)

router = APIRouter(prefix="/cos-otp", tags=["cos-otp-isolation-jit"])


@router.post("/inspect-message", response_model=InspectMessageOtpResponse)
async def inspect_message_otps(
    req: InspectMessageOtpRequest,
    service: CosOtpIsolationJitService = Depends(get_cos_otp_isolation_jit_service),
) -> InspectMessageOtpResponse:
    """Inspect and redact OTP codes from messaging streams before LLM context injection."""
    return service.inspect_message_otps(req)


@router.post("/blackhole-check", response_model=BlackholeCheckResponse)
async def check_recovery_blackhole(
    req: BlackholeCheckRequest,
    service: CosOtpIsolationJitService = Depends(get_cos_otp_isolation_jit_service),
) -> BlackholeCheckResponse:
    """Inspect URLs or message text against password recovery blackhole guardrails."""
    return service.check_recovery_blackhole(req)


@router.post("/jit-tickets/issue", response_model=JitTicketResponse)
async def issue_jit_ticket(
    req: IssueJitTicketRequest,
    service: CosOtpIsolationJitService = Depends(get_cos_otp_isolation_jit_service),
) -> JitTicketResponse:
    """Issue a single-use intent-bound JIT authorization ticket."""
    return service.issue_jit_ticket(req)


@router.post("/jit-tickets/consume", response_model=ConsumeJitTicketResponse)
async def consume_jit_ticket(
    req: ConsumeJitTicketRequest,
    service: CosOtpIsolationJitService = Depends(get_cos_otp_isolation_jit_service),
) -> ConsumeJitTicketResponse:
    """Consume a JIT ticket using burn-after-reading semantics."""
    return service.consume_jit_ticket(req)


@router.post("/quota/evaluate", response_model=EvaluateQuotaResponse)
async def evaluate_quota(
    req: EvaluateQuotaRequest,
    service: CosOtpIsolationJitService = Depends(get_cos_otp_isolation_jit_service),
) -> EvaluateQuotaResponse:
    """Evaluate quota consumption and calculate progressive watermark warnings."""
    return service.evaluate_quota(req)
