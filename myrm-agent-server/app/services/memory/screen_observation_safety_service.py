"""Service layer orchestrating screen observation memory safety, anti-injection, and promotion gate.

[INPUT]
- myrm_agent_harness.toolkits.memory.screen_observation: ScreenObservationMemoryManager, ObservationPayload
- app.schemas.screen_observation_safety: DTOs

[OUTPUT]
- ScreenObservationSafetyService: Singleton service for observation safety
- get_screen_observation_safety_service(): Factory accessor

[POS]
Server business logic layer connecting HTTP API to Harness screen observation safety engine (Topic 01 Item 85).
Strict typing applied: No `any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    ObservationPayload,
    ScreenObservationMemoryManager,
)

from app.schemas.screen_observation_safety import (
    IngestScreenObservationRequest,
    ScreenObservationSafetyResponse,
    ScreenSafetyAuditItemDTO,
    ScreenSafetyAuditListResponse,
)


class ScreenObservationSafetyService:
    """Business service governing untrusted screen evidence isolation, descriptive grammar

    validation, and anti-overpromotion gatekeeping.
    """

    def __init__(self) -> None:
        self._manager = ScreenObservationMemoryManager(
            risk_threshold=0.70,
            min_frequency_count=2,
            min_distinct_sessions=2,
        )

    def process_observation(
        self,
        request: IngestScreenObservationRequest,
    ) -> ScreenObservationSafetyResponse:
        """Process incoming screen observation evidence through the Harness security gate."""
        payload = ObservationPayload(
            source_type=request.source_type,
            raw_text=request.raw_text,
            app_name=request.app_name,
            window_title=request.window_title,
            session_id=request.session_id,
            app_bundle_id=request.app_bundle_id,
        )

        result = self._manager.process_observation(
            payload=payload,
            raw_statement=request.extracted_statement,
        )

        return ScreenObservationSafetyResponse(
            audit_id=result.audit_id,
            is_safe=result.is_safe,
            risk_score=result.evidence.risk_score,
            detected_injection_patterns=result.evidence.detected_injection_patterns,
            promotion_status=result.promotion_status,
            is_promoted=result.gate.is_promoted,
            final_statement=result.final_admitted_statement,
            imperative_detected=result.fact.imperative_detected,
            explanation=result.gate.explanation,
            isolated_prompt_preview=result.evidence.isolated_prompt_segment[:300],
        )

    def get_audit_records(self, limit: int = 50) -> ScreenSafetyAuditListResponse:
        """Retrieve recent security and gate audit records."""
        records = self._manager.get_audit_records(limit=limit)
        dto_list: list[ScreenSafetyAuditItemDTO] = [
            ScreenSafetyAuditItemDTO(
                record_id=r.record_id,
                session_id=r.session_id,
                app_name=r.app_name,
                fact_statement=r.fact_statement,
                promotion_status=r.promotion_status,
                risk_score=r.risk_score,
                imperative_detected=r.imperative_detected,
                created_at=r.created_at.isoformat(),
            )
            for r in records
        ]
        return ScreenSafetyAuditListResponse(
            records=dto_list,
            total_count=len(dto_list),
        )

    def reset_state(self) -> None:
        """Reset internal gate and audit logs (used in testing/maintenance)."""
        self._manager.gate.reset()
        self._manager.clear_audit_records()


_service_instance: ScreenObservationSafetyService | None = None


def get_screen_observation_safety_service() -> ScreenObservationSafetyService:
    """Return the singleton instance of ScreenObservationSafetyService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ScreenObservationSafetyService()
    return _service_instance
