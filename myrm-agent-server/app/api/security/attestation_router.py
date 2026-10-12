"""[INPUT]
- app.services.security.attestation_service::AttestationService (POS: 业务层环境防篡改认证与可信徽章服务)

[OUTPUT]
- GET /security/attestation: 获取当前运行时全向量防篡改可信度报告（提供 WebUI 绿色可信状态徽章）
- POST /security/attestation/verify: 手动触发环境全向量真实性重新验证

[POS]
提供面向 WebUI 与企业管理员的运行时宿主隔离度与外联连接真实性自检与体检报告接口。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.security.attestation_service import AttestationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attestation", tags=["security-attestation"])


class VectorCheckResultResponse(BaseModel):
    vector: str
    target: str
    is_valid: bool
    severity: str
    expected_digest: str | None = None
    actual_digest: str | None = None
    details: dict[str, str]
    error_message: str | None = None


class AttestationReportResponse(BaseModel):
    attestation_id: str
    overall_passed: bool
    checked_at: float
    host_fingerprint: str
    summary: str
    vector_results: list[VectorCheckResultResponse]


@router.get("", response_model=AttestationReportResponse)
async def get_runtime_attestation() -> AttestationReportResponse:
    """Retrieve the latest runtime all-vector security attestation report."""
    report = AttestationService.get_latest_report()
    return AttestationReportResponse(
        attestation_id=report.attestation_id,
        overall_passed=report.overall_passed,
        checked_at=report.checked_at,
        host_fingerprint=report.host_fingerprint,
        summary=report.summary,
        vector_results=[
            VectorCheckResultResponse(
                vector=r.vector.value,
                target=r.target,
                is_valid=r.is_valid,
                severity=r.severity.value,
                expected_digest=r.expected_digest,
                actual_digest=r.actual_digest,
                details=r.details,
                error_message=r.error_message,
            )
            for r in report.vector_results
        ],
    )


@router.post("/verify", response_model=AttestationReportResponse)
async def verify_runtime_attestation() -> AttestationReportResponse:
    """Force on-demand verification of all runtime security vectors."""
    report = AttestationService.verify_environment()
    return AttestationReportResponse(
        attestation_id=report.attestation_id,
        overall_passed=report.overall_passed,
        checked_at=report.checked_at,
        host_fingerprint=report.host_fingerprint,
        summary=report.summary,
        vector_results=[
            VectorCheckResultResponse(
                vector=r.vector.value,
                target=r.target,
                is_valid=r.is_valid,
                severity=r.severity.value,
                expected_digest=r.expected_digest,
                actual_digest=r.actual_digest,
                details=r.details,
                error_message=r.error_message,
            )
            for r in report.vector_results
        ],
    )
