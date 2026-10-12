"""Business service coordinating context fabric extraction, entity linking, and insight sinking.

[INPUT]
- Text payloads, ProjectRegistryEntryDTO, InsightSinkRequestDTO, workspace paths.

[OUTPUT]
- ContextFabricService: orchestrates entity extraction, dynamic project linking, and insight sinking.

[POS]
- Server-side business service for Item 153 CrossSourceWorkContextFabricAndProjectEntityLinkerSuite.
"""

from __future__ import annotations

from pathlib import Path

from app.schemas.context_fabric import (
    EntityMatchResultDTO,
    ExtractEntitiesResponseDTO,
    InsightCandidateDTO,
    InsightSinkRequestDTO,
    InsightSinkResponseDTO,
    LinkEntitiesResponseDTO,
    ProjectRegistryEntryDTO,
    WorkContextEntityDTO,
)
from myrm_agent_harness.toolkits.memory.context_fabric import (
    ContextFabricExtractor,
    InsightCandidate,
    InsightSinkEngine,
    ProjectEntityLinker,
    ProjectRegistryEntry,
)
from myrm_agent_harness.toolkits.memory.project_dongle import (
    DongleBlockType,
    ProjectContextDongleManager,
)


class ContextFabricService:
    """Service providing multi-source context fabric extraction and project linking."""

    def __init__(
        self,
        extractor: ContextFabricExtractor | None = None,
        linker: ProjectEntityLinker | None = None,
        sink_engine: InsightSinkEngine | None = None,
        dongle_manager: ProjectContextDongleManager | None = None,
    ) -> None:
        self.extractor = extractor or ContextFabricExtractor()
        self.linker = linker or ProjectEntityLinker()
        self.dongle_manager = dongle_manager or ProjectContextDongleManager()
        self.sink_engine = sink_engine or InsightSinkEngine(
            linker=self.linker,
            dongle_manager=self.dongle_manager,
        )

    def register_project(self, entry: ProjectRegistryEntryDTO) -> None:
        """Register a new or updated project in the dynamic linker."""
        domain_entry = ProjectRegistryEntry(
            project_id=entry.project_id,
            name=entry.name,
            aliases=tuple(entry.aliases),
            keywords=tuple(entry.keywords),
            description=entry.description,
            status=entry.status,
        )
        self.linker.register_project(domain_entry)

    def list_projects(self) -> list[ProjectRegistryEntryDTO]:
        """Return all registered projects."""
        projects = self.linker.list_projects()
        return [
            ProjectRegistryEntryDTO(
                project_id=p.project_id,
                name=p.name,
                aliases=list(p.aliases),
                keywords=list(p.keywords),
                description=p.description,
                status=p.status,
            )
            for p in projects
        ]

    def extract_entities(self, text: str) -> ExtractEntitiesResponseDTO:
        """Extract structured people, commitments, blockers, and modules from text."""
        domain_entities = self.extractor.extract_from_text(text)
        dtos = [
            WorkContextEntityDTO(
                entity_id=e.entity_id,
                entity_type=e.entity_type,
                name=e.name,
                role_or_relation=e.role_or_relation,
                temporal_anchor=e.temporal_anchor,
                status=e.status,
                confidence=e.confidence,
                evidence_snippet=e.evidence_snippet,
            )
            for e in domain_entities
        ]
        return ExtractEntitiesResponseDTO(entities=dtos, total_count=len(dtos))

    def link_entities(self, text: str, min_confidence: float = 0.4) -> LinkEntitiesResponseDTO:
        """Link text against registered projects."""
        matches = self.linker.link_text(text, min_confidence=min_confidence)
        dtos = [
            EntityMatchResultDTO(
                project_id=m.project_id,
                project_name=m.project_name,
                confidence_score=m.confidence_score,
                matched_terms=list(m.matched_terms),
                evidence_snippet=m.evidence_snippet,
                is_definitive=m.is_definitive,
            )
            for m in matches
        ]
        top_id = dtos[0].project_id if dtos else None
        return LinkEntitiesResponseDTO(matches=dtos, top_project_id=top_id)

    def sink_insight(self, request: InsightSinkRequestDTO) -> InsightSinkResponseDTO:
        """Sink an extracted insight into targeted project memory."""
        cand_dto: InsightCandidateDTO = request.candidate
        domain_cand = InsightCandidate(
            insight_id=cand_dto.insight_id,
            title=cand_dto.title,
            content=cand_dto.content,
            source_event_ids=tuple(cand_dto.source_event_ids),
            target_project_id=cand_dto.target_project_id,
            impact_level=cand_dto.impact_level,
        )

        file_type_map = {
            "PROJECT_STATE.md": DongleBlockType.PROJECT_STATE,
            "DECISIONS.md": DongleBlockType.DECISIONS,
            "LESSONS.md": DongleBlockType.LESSONS,
            "INDEX.md": DongleBlockType.INDEX,
        }
        target_type = file_type_map.get(request.target_file_type, DongleBlockType.PROJECT_STATE)

        record = self.sink_engine.sink_insight(
            domain_cand,
            workspace_dir=request.workspace_dir,
            target_file_type=target_type,
        )

        if not record:
            return InsightSinkResponseDTO(
                success=False,
                message="Failed to establish confident project attribution for insight.",
            )

        return InsightSinkResponseDTO(
            success=True,
            record_id=record.record_id,
            project_id=record.project_id,
            sink_target=record.sink_target,
            provenance_tag=record.provenance_tag,
            rendered_bullet=record.rendered_bullet,
            message="Insight successfully sunken into project memory.",
        )
