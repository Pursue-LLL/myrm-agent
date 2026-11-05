"""Consolidation (Umbrella Merge) integration for the curator service.

[INPUT]
- myrm_agent_harness.agent.skills.curator::SkillCurator (POS: Stateless curator engine)
- myrm_agent_harness.agent.skills.curator.consolidation::ConsolidationPlan (POS: Plan type)
- app.core.skills.curator.service::_get_sweep_lock, get_curator_config, get_stats_collector (POS: Shared curator state)
- app.core.skills.curator.bound_skills::bound_skill_names (POS: Skills bound by agent profiles, cron jobs and kanban tasks)
- app.core.skills.curator.local_skills::scan_local_skills (POS: Scan of all skill roots with installed-skill marking)
- app.core.skills.creation.service::skill_creation_service (POS: SkillWriteBackend)

[OUTPUT]
- run_consolidation_preview: Dry-run consolidation plan; an error when the judge could not evaluate groups and nothing else is proposed
- run_consolidation_execute: Apply a previewed plan exactly as previewed, without another model call

[POS]
Curator consolidation business service. Shares the sweep lock and curator
config with the main curator service so preview/execute stay mutually
exclusive with background sweeps. Skills bound by an agent, a cron job or a
kanban task never take part, so nothing that references a skill is rewritten.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .bound_skills import bound_skill_names
from .local_skills import scan_local_skills
from .service import _get_sweep_lock, get_curator_config, get_stats_collector

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from myrm_agent_harness.agent.skills.curator.consolidation import ConsolidationPlan
    from myrm_agent_harness.backends.skills.creation_protocols import SkillWriteBackend


async def _get_consolidation_deps() -> tuple[BaseChatModel, SkillWriteBackend]:
    """Resolve the llm and write_backend for consolidation.

    Raises HTTPException 503 if the LLM is not configured.
    """
    from fastapi import HTTPException
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.skills.creation.service import skill_creation_service
    from app.services.agent.platform_config import load_platform_model_config

    try:
        platform_model = await load_platform_model_config()
        llm = await llm_manager.get_llm_from_config(platform_model)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured",
        ) from exc

    return llm, skill_creation_service


async def run_consolidation_preview() -> ConsolidationPlan:
    """Propose a consolidation plan without executing it.

    Raises HTTPException 502 when the plan is empty only because the judge could not evaluate some skill
    groups: an empty plan reads as "well-organized", which would not be true.
    """
    from fastapi import HTTPException
    from myrm_agent_harness.agent.skills.curator import SkillCurator
    from myrm_agent_harness.agent.skills.curator.consolidation import ConsolidationPlan

    async with _get_sweep_lock():
        llm, write_backend = await _get_consolidation_deps()
        config = get_curator_config()
        collector = get_stats_collector()

        curator = SkillCurator(collector, config, llm=llm, write_backend=write_backend)

        scan = await scan_local_skills()
        if not scan.skills:
            return ConsolidationPlan()

        protected_names = await bound_skill_names(scan.skills)
        _, plan = await curator.run_async(
            scan.skills,
            force=True,
            protected_names=protected_names,
            installed_names=scan.installed_names,
        )
        if not isinstance(plan, ConsolidationPlan):
            return ConsolidationPlan()

        if plan.is_empty and plan.failed_clusters:
            raise HTTPException(
                status_code=502,
                detail=f"Consolidation judge could not evaluate {plan.failed_clusters} skill group(s)",
            )

        return plan


def _no_changes(summary: str) -> dict[str, int | str]:
    return {
        "success_count": 0,
        "failure_count": 0,
        "total_archived": 0,
        "total_created": 0,
        "net_reduction": 0,
        "summary": summary,
    }


async def run_consolidation_execute(plan: ConsolidationPlan) -> dict[str, int | str]:
    """Apply a previewed plan and return the structured response.

    The model is not asked again: the plan is the one the user saw. It may be older than this call, so the curator
    leaves alone every skill the plan names that has since been pinned, archived or bound.
    """
    from myrm_agent_harness.agent.skills.curator import SkillCurator

    async with _get_sweep_lock():
        llm, write_backend = await _get_consolidation_deps()
        config = get_curator_config()
        collector = get_stats_collector()

        curator = SkillCurator(collector, config, llm=llm, write_backend=write_backend)

        scan = await scan_local_skills()
        if not scan.skills:
            return _no_changes("No skills available for consolidation.")

        protected_names = await bound_skill_names(scan.skills)
        report = await curator.apply_consolidation_plan(
            scan.skills,
            plan,
            protected_names=protected_names,
            installed_names=scan.installed_names,
        )

    if report is None:
        return _no_changes("Consolidation not needed or unavailable.")

    return {
        "success_count": report.success_count,
        "failure_count": report.failure_count,
        "total_archived": report.total_archived,
        "total_created": report.total_created,
        "net_reduction": report.net_reduction,
        "summary": report.to_summary(),
    }
