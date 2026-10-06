"""
[POS] app/services/memory/memory_dual_track_service.py
[INPUT] threading.Lock, myrm_agent_harness.toolkits.memory.dual_track_extraction, app.schemas.memory_dual_track
[OUTPUT] MemoryDualTrackService, get_memory_dual_track_service

Business service implementing dual-track fact and procedural extraction, anti-silent-drop reporting, and local rule persistence.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from threading import Lock

from myrm_agent_harness.toolkits.memory.dual_track_extraction import (
    DualTrackExtractionGateway,
    ExtractedProceduralRule,
    ExtractedUserFact,
    ExtractionDestinyReport,
)

from app.schemas.memory_dual_track import (
    ExtractDualTrackRequestDTO,
    ExtractedProceduralRuleDTO,
    ExtractedUserFactDTO,
    ExtractionDestinyReportDTO,
)

logger = logging.getLogger(__name__)


class MemoryDualTrackService:
    """Service mediating dual-track extraction gateway and maintaining persistent rules/facts registry."""

    def __init__(self, gateway: DualTrackExtractionGateway | None = None) -> None:
        self._lock: Lock = Lock()
        self._gateway: DualTrackExtractionGateway = gateway or DualTrackExtractionGateway()
        self._stored_rules: dict[str, ExtractedProceduralRuleDTO] = {}
        self._stored_facts: dict[str, ExtractedUserFactDTO] = {}

    @property
    def gateway(self) -> DualTrackExtractionGateway:
        """Access underlying gateway instance."""
        return self._gateway

    def extract_and_route(
        self,
        request: ExtractDualTrackRequestDTO,
    ) -> ExtractionDestinyReportDTO:
        """Process interaction text through dual-track gateway and optionally persist results."""
        report: ExtractionDestinyReport = self._gateway.process_utterance(
            text=request.text,
            domain=request.domain,
        )

        facts_dtos: list[ExtractedUserFactDTO] = [
            self._convert_fact_to_dto(f) for f in report.extracted_facts
        ]
        rules_dtos: list[ExtractedProceduralRuleDTO] = [
            self._convert_rule_to_dto(r) for r in report.extracted_rules
        ]

        if request.auto_persist:
            with self._lock:
                for rule_dto in rules_dtos:
                    self._stored_rules[rule_dto.rule_id] = rule_dto
                for fact_dto in facts_dtos:
                    self._stored_facts[fact_dto.fact_id] = fact_dto

        logger.info(
            "Dual-track extraction complete: destiny=%s, rules=%d, facts=%d",
            report.destiny.value,
            len(rules_dtos),
            len(facts_dtos),
        )

        return ExtractionDestinyReportDTO(
            destiny=report.destiny.value,
            track=report.track.value,
            discard_reason=report.discard_reason,
            raw_input_text=report.raw_input_text,
            processed_at=report.processed_at,
            extracted_facts=facts_dtos,
            extracted_rules=rules_dtos,
        )

    def list_rules(self) -> list[ExtractedProceduralRuleDTO]:
        """Return all persisted procedural rules."""
        with self._lock:
            return list(self._stored_rules.values())

    def get_rule(self, rule_id: str) -> ExtractedProceduralRuleDTO | None:
        """Retrieve single procedural rule by identifier."""
        with self._lock:
            return self._stored_rules.get(rule_id)

    def list_facts(self) -> list[ExtractedUserFactDTO]:
        """Return all persisted facts."""
        with self._lock:
            return list(self._stored_facts.values())

    def clear(self) -> None:
        """Clear all in-memory persistent rules and facts (primarily for testing)."""
        with self._lock:
            self._stored_rules.clear()
            self._stored_facts.clear()

    @staticmethod
    def _convert_rule_to_dto(rule: ExtractedProceduralRule) -> ExtractedProceduralRuleDTO:
        return ExtractedProceduralRuleDTO(
            rule_id=rule.rule_id,
            name=rule.name,
            trigger_condition=rule.trigger_condition,
            action_guideline=rule.action_guideline,
            domain=rule.domain,
            confidence=rule.confidence,
            raw_source=rule.raw_source,
        )

    @staticmethod
    def _convert_fact_to_dto(fact: ExtractedUserFact) -> ExtractedUserFactDTO:
        return ExtractedUserFactDTO(
            fact_id=fact.fact_id,
            entity=fact.entity,
            attribute=fact.attribute,
            value=fact.value,
            confidence=fact.confidence,
            raw_source=fact.raw_source,
        )


_global_dual_track_service: MemoryDualTrackService | None = None
_service_init_lock: Lock = Lock()


def get_memory_dual_track_service() -> MemoryDualTrackService:
    """Singleton provider for MemoryDualTrackService."""
    global _global_dual_track_service
    if _global_dual_track_service is None:
        with _service_init_lock:
            if _global_dual_track_service is None:
                _global_dual_track_service = MemoryDualTrackService()
    return _global_dual_track_service
