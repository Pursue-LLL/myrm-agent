"""Business service coordinating project experience extraction, causal flywheel ingestion, and minefield pre-sniffing.

[INPUT]
- Narrative strings, IngestExperienceRequestDTO payloads, SniffMinefieldRequestDTO queries.

[OUTPUT]
- ExperienceFlywheelService: provides unified experience extraction, flywheel storage, and proactive alerts.

[POS]
- Server-side business service for Item 154 ProjectExperienceAndADRFlywheelSuite.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.experience_flywheel import (
    BugExperienceAndADRExtractor,
    CausalFlywheelStore,
    EngineeringExperience,
    ExperienceKind,
    MinefieldPreSniffingGuard,
)
from myrm_agent_harness.toolkits.memory.project_dongle import ProjectContextDongleManager

from app.schemas.experience_flywheel import (
    EngineeringExperienceDTO,
    ExtractExperienceResponseDTO,
    IngestExperienceRequestDTO,
    IngestExperienceResponseDTO,
    MinefieldAlertDTO,
    SniffMinefieldRequestDTO,
    SniffMinefieldResponseDTO,
)


class ExperienceFlywheelService:
    """Service orchestrating engineering knowledge flywheel, Bug/ADR extraction, and minefield guards."""

    def __init__(
        self,
        extractor: BugExperienceAndADRExtractor | None = None,
        store: CausalFlywheelStore | None = None,
        guard: MinefieldPreSniffingGuard | None = None,
        dongle_manager: ProjectContextDongleManager | None = None,
    ) -> None:
        self.extractor = extractor or BugExperienceAndADRExtractor()
        self.dongle_manager = dongle_manager or ProjectContextDongleManager()
        self.store = store or CausalFlywheelStore(dongle_manager=self.dongle_manager)
        self.guard = guard or MinefieldPreSniffingGuard(flywheel_store=self.store)

    def extract_experiences(
        self,
        narrative: str,
        default_kind_str: str = "bug_experience",
    ) -> ExtractExperienceResponseDTO:
        """Extract structured Bug experiences and ADR items from task narratives."""
        kind_map = {
            "bug_experience": ExperienceKind.BUG_EXPERIENCE,
            "architectural_decision": ExperienceKind.ARCHITECTURAL_DECISION,
            "convention_rule": ExperienceKind.CONVENTION_RULE,
        }
        default_kind = kind_map.get(default_kind_str, ExperienceKind.BUG_EXPERIENCE)
        extracted = self.extractor.extract_from_trace(narrative, default_kind=default_kind)

        dtos = [
            EngineeringExperienceDTO(
                experience_id=e.experience_id,
                kind=e.kind.value,
                target_entity=e.target_entity,
                trigger_condition=e.trigger_condition,
                root_cause_or_rationale=e.root_cause_or_rationale,
                convention_or_remedy=e.convention_or_remedy,
                created_date=e.created_date,
                tags=list(e.tags),
                confidence=e.confidence,
            )
            for e in extracted
        ]
        return ExtractExperienceResponseDTO(experiences=dtos, total_count=len(dtos))

    def ingest_experience(
        self,
        request: IngestExperienceRequestDTO,
    ) -> IngestExperienceResponseDTO:
        """Ingest an experience into the causal flywheel and optionally sync to worktree dongles."""
        dto = request.experience
        kind_map = {
            "bug_experience": ExperienceKind.BUG_EXPERIENCE,
            "architectural_decision": ExperienceKind.ARCHITECTURAL_DECISION,
            "convention_rule": ExperienceKind.CONVENTION_RULE,
        }
        kind = kind_map.get(dto.kind, ExperienceKind.BUG_EXPERIENCE)

        domain_exp = EngineeringExperience(
            experience_id=dto.experience_id,
            kind=kind,
            target_entity=dto.target_entity,
            trigger_condition=dto.trigger_condition,
            root_cause_or_rationale=dto.root_cause_or_rationale,
            convention_or_remedy=dto.convention_or_remedy,
            created_date=dto.created_date,
            tags=tuple(dto.tags),
            confidence=dto.confidence,
        )

        res = self.store.ingest_experience(domain_exp, workspace_dir=request.workspace_dir)

        return IngestExperienceResponseDTO(
            experience_id=res.experience_id,
            kind=res.kind.value,
            target_entity=res.target_entity,
            bound_dongle_block_id=res.bound_dongle_block_id,
            persisted=res.persisted,
            message=res.message,
        )

    def list_experiences(self, kind_str: str | None = None) -> list[EngineeringExperienceDTO]:
        """List experiences from store, optionally filtered by kind."""
        kind_map = {
            "bug_experience": ExperienceKind.BUG_EXPERIENCE,
            "architectural_decision": ExperienceKind.ARCHITECTURAL_DECISION,
            "convention_rule": ExperienceKind.CONVENTION_RULE,
        }
        kind = kind_map.get(kind_str) if kind_str else None
        items = self.store.list_all(kind=kind)

        return [
            EngineeringExperienceDTO(
                experience_id=e.experience_id,
                kind=e.kind.value,
                target_entity=e.target_entity,
                trigger_condition=e.trigger_condition,
                root_cause_or_rationale=e.root_cause_or_rationale,
                convention_or_remedy=e.convention_or_remedy,
                created_date=e.created_date,
                tags=list(e.tags),
                confidence=e.confidence,
            )
            for e in items
        ]

    def sniff_minefield(
        self,
        request: SniffMinefieldRequestDTO,
    ) -> SniffMinefieldResponseDTO:
        """Pre-sniff upcoming execution plan and candidate entities against historical minefields."""
        alerts = self.guard.sniff(
            plan_text=request.plan_text,
            explicit_entities=request.explicit_entities,
        )
        alert_dtos = [
            MinefieldAlertDTO(
                entity_matched=a.entity_matched,
                experience_id=a.experience_id,
                kind=a.kind.value,
                warning_message=a.warning_message,
                convention_to_follow=a.convention_to_follow,
                severity=a.severity,
            )
            for a in alerts
        ]
        prompt = self.guard.format_alerts_prompt(alerts)
        has_critical = any(a.severity == "critical" for a in alerts)

        return SniffMinefieldResponseDTO(
            alerts=alert_dtos,
            advisory_prompt=prompt,
            has_critical_alerts=has_critical,
        )
