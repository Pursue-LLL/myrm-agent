"""Skill consolidation orchestrator — coordinates the full pipeline.

Wires together ClusterDetector → ConsolidationJudge → ConsolidationExecutor into two separate steps:
``propose`` produces a plan and executes nothing, ``apply`` carries out a plan it is handed.

[INPUT]
- .cluster_detector::ClusterDetector (POS: Cluster detection layer.)
- .judge::ConsolidationJudge (POS: LLM judge layer.)
- .executor::ConsolidationExecutor (POS: Execution layer.)
- .types::ConsolidationPlan, ConsolidationReport, is_consolidation_eligible (POS: consolidation types.)
- backends.skills.types::SkillMetadata (POS: Skill types.)
- backends.skills.stats_collector::SkillStatsCollector (POS: Stats collector.)
- backends.skills.creation_protocols::SkillWriteBackend (POS: Write backend.)
- langchain_core.language_models::BaseChatModel (POS: LLM base class.)

[OUTPUT]
- SkillConsolidator: Top-level orchestrator for the consolidation pipeline.

[POS]
Top-level orchestrator. Single entry point for skill consolidation: propose a plan, then apply it when the host decides.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .cluster_detector import ClusterDetector
from .executor import ConsolidationExecutor
from .judge import ConsolidationJudge
from .types import ConsolidationPlan, ConsolidationReport, is_consolidation_eligible

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from myrm_agent_harness.backends.skills.creation_protocols import SkillWriteBackend
    from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)

_DEFAULT_MIN_SKILLS_FOR_CONSOLIDATION = 10
_DEFAULT_MIN_CLUSTER_SIZE = 3


class SkillConsolidator:
    """Top-level orchestrator for the skill consolidation pipeline.

    Two steps, so the host can show a plan before anything changes:
    - ``propose``: filter the eligible skills (active, non-pinned, non-protected), group those that share a name
      prefix into candidate clusters and let the LLM judge each one. The result is a ConsolidationPlan; nothing
      is executed.
    - ``apply``: carry out a ConsolidationPlan and return a ConsolidationReport. The LLM is not asked again, so
      what runs is what was proposed.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        write_backend: SkillWriteBackend,
        stats_collector: SkillStatsCollector,
        *,
        min_skills_for_consolidation: int = _DEFAULT_MIN_SKILLS_FOR_CONSOLIDATION,
        min_cluster_size: int = _DEFAULT_MIN_CLUSTER_SIZE,
    ) -> None:
        self._detector = ClusterDetector(min_cluster_size=min_cluster_size)
        self._judge = ConsolidationJudge(llm)
        self._write_backend = write_backend
        self._stats_collector = stats_collector
        self._min_skills = min_skills_for_consolidation

    async def propose(
        self,
        skills: list[SkillMetadata],
        *,
        reserved_names: frozenset[str] = frozenset(),
    ) -> ConsolidationPlan:
        """Plan the consolidation of ``skills``; nothing is executed.

        Args:
            skills: All skills from the skill backend.
            reserved_names: Skills the host keeps out of this run and so leaves out of ``skills``. No umbrella
                may take their names.

        Returns:
            The plan; empty when there are too few eligible skills, no cluster or nothing the judge would act on.
        """
        eligible = self._filter_eligible(skills)

        if len(eligible) < self._min_skills:
            logger.info(
                "Consolidation skipped: only %d eligible skills (minimum: %d)",
                len(eligible),
                self._min_skills,
            )
            return ConsolidationPlan()

        clusters = self._detector.detect(eligible)
        if not clusters:
            logger.info("Consolidation: no clusters detected")
            return ConsolidationPlan()

        plan = await self._judge.judge_clusters(clusters, skills, reserved_names=reserved_names)

        if plan.is_empty:
            logger.info("Consolidation: judge proposed no actions")
        else:
            logger.info(
                "Consolidation plan: %d actions, %d skills affected, estimated reduction: %d",
                len(plan.actions),
                plan.total_skills_affected,
                plan.estimated_reduction,
            )
        return plan

    async def apply(
        self,
        plan: ConsolidationPlan,
        skills: list[SkillMetadata],
        *,
        reserved_names: frozenset[str] = frozenset(),
    ) -> ConsolidationReport:
        """Carry out ``plan`` as it is; the judge is not asked again.

        Args:
            plan: A plan ``propose`` returned.
            skills: The skills as they are now, not as they were when the plan was made: the executor leaves
                alone every skill the plan names that has since stopped being eligible.
            reserved_names: See ``propose``.

        Returns:
            What was done, action by action.
        """
        executor = ConsolidationExecutor(
            self._write_backend,
            self._stats_collector,
            skills,
            reserved_names=reserved_names,
        )
        return await executor.execute(plan.actions)

    @staticmethod
    def _filter_eligible(skills: list[SkillMetadata]) -> list[SkillMetadata]:
        """Filter skills eligible for consolidation analysis (see ``is_consolidation_eligible``)."""
        return [s for s in skills if is_consolidation_eligible(s)]
