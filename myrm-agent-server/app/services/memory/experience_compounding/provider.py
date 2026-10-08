"""Service provider for Experience Compounding and Knowledge Condensation Suite.

[POS]
Maintains singleton instance of ExperienceCompoundingSuite, orchestrates experience
reinforcement, semantic Golden Rule synthesis, and active lease annealing.

[INPUT]
- typing, logging
- myrm_agent_harness.toolkits.memory (ExperienceCompoundingSuite)
- app.schemas.experience_compounding (AddExperienceItemRequest, AnnealingResponseDTO,
  CompoundedExperienceItemDTO, CondensationResponseDTO, DecondenseRuleRequest,
  ExperienceCompoundingStatsResponse, GoldenRuleDTO, ReinforceExperienceRequest)

[OUTPUT]
- ExperienceCompoundingServiceProvider, get_experience_compounding_service
"""

from __future__ import annotations

import logging
from typing import ClassVar

from myrm_agent_harness.toolkits.memory import ExperienceCompoundingSuite

from app.schemas.experience_compounding import (
    AddExperienceItemRequest,
    AnnealingResponseDTO,
    CompoundedExperienceItemDTO,
    CondensationResponseDTO,
    DecondenseRuleRequest,
    ExperienceCompoundingStatsResponse,
    GoldenRuleDTO,
    ReinforceExperienceRequest,
)

logger = logging.getLogger(__name__)


class ExperienceCompoundingServiceProvider:
    """Manages the lifecycle and business logic of experience compounding and condensation."""

    _instance: ClassVar[ExperienceCompoundingServiceProvider | None] = None

    def __init__(self) -> None:
        self._suite = ExperienceCompoundingSuite()
        self._bootstrap_seeded_experiences()

    def _bootstrap_seeded_experiences(self) -> None:
        """Seed baseline personal habits and transient contexts."""
        self._suite.add_item(
            content="前端界面排版优先使用 TailwindCSS 紧凑原子样式",
            topic="frontend",
            base_weight=1.0,
            tags=["ui", "css"],
            item_id="seed-fe-1",
        )
        self._suite.add_item(
            content="前端界面排版优先使用 Flexbox 弹性布局样式",
            topic="frontend",
            base_weight=1.0,
            tags=["ui", "layout"],
            item_id="seed-fe-2",
        )
        self._suite.add_item(
            content="Python 代码严格禁止使用 Any 类型注解与私有深层导入",
            topic="quality",
            base_weight=1.5,
            is_pinned=True,  # Active lease
            tags=["typing", "architecture", "pinned"],
            item_id="seed-qual-1",
        )
        self._suite.add_item(
            content="排查本地 Vite 调试端口 5173 偶发占用问题",
            topic="debug",
            base_weight=1.0,
            is_temporary=True,  # Transient context
            tags=["temporary", "port"],
            item_id="seed-dbg-1",
        )
        logger.info("Bootstrapped baseline experiences in ExperienceCompoundingServiceProvider")

    def add_experience(
        self, request: AddExperienceItemRequest
    ) -> CompoundedExperienceItemDTO:
        """Register a new experience item into the suite."""
        item = self._suite.add_item(
            content=request.content,
            topic=request.topic,
            base_weight=request.base_weight,
            is_temporary=request.is_temporary,
            is_pinned=request.is_pinned,
            tags=request.tags,
            item_id=request.item_id,
        )
        return CompoundedExperienceItemDTO(
            item_id=item.item_id,
            content=item.content,
            topic=item.topic,
            base_weight=item.base_weight,
            compounded_weight=item.compounded_weight,
            hit_count=item.hit_count,
            adoption_count=item.adoption_count,
            state=item.state.value,
            half_life_days=item.half_life_days,
            is_pinned=item.is_pinned,
            is_temporary=item.is_temporary,
            tags=item.tags,
        )

    def reinforce(self, request: ReinforceExperienceRequest) -> float:
        """Reinforce the compounding weight of an experience item."""
        return self._suite.reinforce(item_id=request.item_id, adopted=request.adopted)

    def condense(self) -> CondensationResponseDTO:
        """Condense scattered active fragments into Golden Rules."""
        new_rules, report = self._suite.condense()
        rule_dtos = [
            GoldenRuleDTO(
                rule_id=r.rule_id,
                topic=r.topic,
                rule_statement=r.rule_statement,
                rationale=r.rationale,
                confidence_score=r.confidence_score,
                source_fragment_ids=r.source_fragment_ids,
            )
            for r in new_rules
        ]
        return CondensationResponseDTO(
            report_id=report.report_id,
            rules_generated=rule_dtos,
            clusters_found=report.clusters_found,
            fragments_archived=report.fragments_archived,
            compression_ratio=report.compression_ratio,
            details=report.details,
        )

    def decondense(
        self, request: DecondenseRuleRequest
    ) -> list[CompoundedExperienceItemDTO]:
        """Roll back a Golden Rule and reactivate its archived fragments."""
        reactivated = self._suite.decondense(rule_id=request.rule_id)
        return [
            CompoundedExperienceItemDTO(
                item_id=it.item_id,
                content=it.content,
                topic=it.topic,
                base_weight=it.base_weight,
                compounded_weight=it.compounded_weight,
                hit_count=it.hit_count,
                adoption_count=it.adoption_count,
                state=it.state.value,
                half_life_days=it.half_life_days,
                is_pinned=it.is_pinned,
                is_temporary=it.is_temporary,
                tags=it.tags,
            )
            for it in reactivated
        ]

    def anneal(self) -> AnnealingResponseDTO:
        """Run obsolete context annealing and cold tiering."""
        report = self._suite.anneal()
        return AnnealingResponseDTO(
            report_id=report.report_id,
            inspected_count=report.inspected_count,
            active_lease_exempt_count=report.active_lease_exempt_count,
            cold_tiered_count=report.cold_tiered_count,
            decayed_items=report.decayed_items,
        )

    def list_active(self) -> list[CompoundedExperienceItemDTO]:
        """Return all hot active experience items."""
        return [
            CompoundedExperienceItemDTO(
                item_id=it.item_id,
                content=it.content,
                topic=it.topic,
                base_weight=it.base_weight,
                compounded_weight=it.compounded_weight,
                hit_count=it.hit_count,
                adoption_count=it.adoption_count,
                state=it.state.value,
                half_life_days=it.half_life_days,
                is_pinned=it.is_pinned,
                is_temporary=it.is_temporary,
                tags=it.tags,
            )
            for it in self._suite.list_active_items()
        ]

    def list_rules(self) -> list[GoldenRuleDTO]:
        """Return all active Golden Rules."""
        return [
            GoldenRuleDTO(
                rule_id=r.rule_id,
                topic=r.topic,
                rule_statement=r.rule_statement,
                rationale=r.rationale,
                confidence_score=r.confidence_score,
                source_fragment_ids=r.source_fragment_ids,
            )
            for r in self._suite.list_golden_rules()
        ]

    def get_stats(self) -> ExperienceCompoundingStatsResponse:
        """Return operational metrics across the compounding suite."""
        raw = self._suite.get_stats()
        return ExperienceCompoundingStatsResponse(
            total_items=int(raw["total_items"]),
            active_items=int(raw["active_items"]),
            condensed_items=int(raw["condensed_items"]),
            cold_tiered_items=int(raw["cold_tiered_items"]),
            golden_rules_count=int(raw["golden_rules_count"]),
            average_compounded_weight=float(raw["average_compounded_weight"]),
        )


def get_experience_compounding_service() -> ExperienceCompoundingServiceProvider:
    """Return the global singleton instance of ExperienceCompoundingServiceProvider."""
    if ExperienceCompoundingServiceProvider._instance is None:
        ExperienceCompoundingServiceProvider._instance = (
            ExperienceCompoundingServiceProvider()
        )
    return ExperienceCompoundingServiceProvider._instance
