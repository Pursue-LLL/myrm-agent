"""Service orchestrating Data Plane Injection Defense, Hardened Fencing, and QuotedAsData Badge Projections.

[INPUT]
- FencePayloadRequest, DetectInjectionRequest
- Harness HardenedDataFence, TwoPlaneInjectionDetector

[OUTPUT]
- DataPlaneDefenseService: enterprise service handling data fencing and QuotedAsData badge metadata.

[POS]
Server service layer. Neutralizes indirect prompt injections from third-party data and prepares UI trust badges.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.data_plane_defense import (
    DataPlaneThreatFinding,
    HardenedDataFence,
    InjectionPlaneType,
    SanitizedQuoteResult,
    TwoPlaneInjectionDetector,
)

from app.schemas.data_plane_defense import (
    DataPlaneThreatFindingDto,
    DetectInjectionRequest,
    DetectInjectionResponse,
    FencePayloadRequest,
    FencePayloadResponse,
    QuotedAsDataBadgeDto,
)

logger = logging.getLogger(__name__)


def _finding_to_dto(domain: DataPlaneThreatFinding) -> DataPlaneThreatFindingDto:
    """Map domain threat finding to Pydantic DTO."""
    return DataPlaneThreatFindingDto(
        threat_type=domain.threat_type,
        pattern_matched=domain.pattern_matched,
        raw_snippet=domain.raw_snippet,
        sanitized_replacement=domain.sanitized_replacement,
    )


def _sanitized_result_to_dto(domain: SanitizedQuoteResult) -> FencePayloadResponse:
    """Map domain SanitizedQuoteResult to Pydantic DTO."""
    return FencePayloadResponse(
        sanitized_text=domain.sanitized_text,
        enclosed_payload=domain.enclosed_payload,
        subject=domain.subject,
        source=domain.source,
        original_length=domain.original_length,
        sanitized_length=domain.sanitized_length,
        stripped_turns_count=domain.stripped_turns_count,
        removed_control_chars_count=domain.removed_control_chars_count,
        is_truncated=domain.is_truncated,
        findings=[_finding_to_dto(f) for f in domain.findings],
        sanitized_at=domain.sanitized_at,
    )


class DataPlaneDefenseService:
    """Singleton service providing data fencing and prompt injection inspection."""

    def fence_data(self, request: FencePayloadRequest) -> FencePayloadResponse:
        """Sanitize external untrusted text and generate safe enclosed XML boundary representation."""
        result = HardenedDataFence.fence_payload(
            raw_text=request.raw_text,
            subject=request.subject,
            source=request.source,
            max_fenced_chars=request.max_fenced_chars,
        )
        return _sanitized_result_to_dto(result)

    def detect_injection(self, request: DetectInjectionRequest) -> DetectInjectionResponse:
        """Detect prompt injection attacks across user-plane or data-plane surfaces."""
        plane = (
            InjectionPlaneType.USER_PLANE
            if request.plane.lower() == "user_plane"
            else InjectionPlaneType.DATA_PLANE
        )
        result = TwoPlaneInjectionDetector.detect(text=request.text, plane=plane)
        return DetectInjectionResponse(
            plane=str(result.plane),
            is_suspicious=result.is_suspicious,
            risk_score=result.risk_score,
            detected_rules=list(result.detected_rules),
            findings=[_finding_to_dto(f) for f in result.findings],
            analyzed_at=result.analyzed_at,
        )

    def generate_quoted_badge(
        self,
        raw_text: str,
        subject: str = "外部数据",
        source: str = "第三方数据源",
    ) -> QuotedAsDataBadgeDto:
        """Produce safe frontend trust badge metadata for unendorsed external data."""
        fenced = HardenedDataFence.fence_payload(raw_text=raw_text, subject=subject, source=source)
        disclaimer = f"{subject}：内容由外部提供，原样展示，未经官方认证"
        return QuotedAsDataBadgeDto(
            subject=subject,
            source=source,
            sanitized_content=fenced.sanitized_text,
            is_verified_untrusted_quote=True,
            disclaimer=disclaimer,
        )


# Global singleton instance
default_data_plane_defense_service = DataPlaneDefenseService()
