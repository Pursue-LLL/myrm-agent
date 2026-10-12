"""Service layer for knowledge graph pre-extraction content screening and anti-poisoning.

[INPUT]
- app.schemas.kg_screening::* (POS: schemas)
- myrm_agent_harness.toolkits.memory.kg_screening.* (POS: harness shield)

[OUTPUT]
- KGScreeningService: Business service executing content compliance and injection shielding
- get_kg_screening_service: FastAPI dependency provider

[POS]
Server-side bridge connecting frontend UI/extraction pipelines with harness KG poisoning shield.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory.kg_screening.shield import (
    KnowledgeGraphPoisoningShield,
)
from myrm_agent_harness.toolkits.memory.kg_screening.types import (
    ScreeningAuditRecord,
    ScreeningResult,
)

from app.schemas.kg_screening import (
    ScreenContentRequestDTO,
    ScreenContentResponseDTO,
    ScreeningAuditListResponseDTO,
    ScreeningAuditRecordDTO,
    ThreatFindingDTO,
)

logger = logging.getLogger(__name__)


class KGScreeningService:
    """Provides application-level execution of pre-extraction content screening."""

    def __init__(
        self,
        shield: KnowledgeGraphPoisoningShield | None = None,
    ) -> None:
        self.shield = shield or KnowledgeGraphPoisoningShield()

    def screen_content(
        self, request: ScreenContentRequestDTO
    ) -> ScreenContentResponseDTO:
        """Screen and sanitize raw text before feeding to knowledge graph extraction."""
        result: ScreeningResult = self.shield.screen_text(
            text=request.text,
            source_uri=request.source_uri,
            sanitize_if_possible=request.sanitize_if_possible,
        )

        findings_dtos = [
            ThreatFindingDTO(
                category=f.category.value,
                matched_pattern=f.matched_pattern,
                snippet=f.snippet,
                position=f.position,
                risk_level=f.risk_level,
                description=f.description,
            )
            for f in result.findings
        ]

        return ScreenContentResponseDTO(
            verdict=result.verdict.value,
            is_blocked=result.is_blocked,
            findings=findings_dtos,
            original_length=result.original_length,
            sanitized_content=result.sanitized_content,
            risk_score=round(result.risk_score, 3),
        )

    def get_audit_records(
        self, limit: int = 50
    ) -> ScreeningAuditListResponseDTO:
        """Retrieve historical security audit logs for screening events."""
        records: list[ScreeningAuditRecord] = self.shield.get_audit_records(limit=limit)

        record_dtos = [
            ScreeningAuditRecordDTO(
                audit_id=r.audit_id,
                timestamp=r.timestamp,
                source_uri=r.source_uri,
                verdict=r.verdict.value,
                risk_score=round(r.risk_score, 3),
                findings_count=r.findings_count,
                findings_summary=r.findings_summary,
                sanitized_applied=r.sanitized_applied,
            )
            for r in records
        ]

        return ScreeningAuditListResponseDTO(
            records=record_dtos,
            total_count=len(record_dtos),
        )


_service_instance: KGScreeningService | None = None


def get_kg_screening_service() -> KGScreeningService:
    """Dependency provider for KGScreeningService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = KGScreeningService()
    return _service_instance
