"""Consolidation (Umbrella Merge) integration for the curator service.

[INPUT]
- myrm_agent_harness.agent.skills.curator::SkillCurator (POS: Stateless curator engine)
- myrm_agent_harness.agent.skills.curator.consolidation::ConsolidationPlan/ConsolidationReport (POS: Plan/report types)
- app.core.skills.curator.service::_get_sweep_lock, get_curator_config, get_stats_collector (POS: Shared curator state)
- app.core.skills.curator.bound_skills::bound_skill_names (POS: Skills bound by agent profiles, cron jobs and kanban tasks)
- app.core.skills.curator.local_skills::scan_local_skills (POS: Scan of all skill roots with installed-skill marking)
- app.core.skills.creation.service::skill_creation_service (POS: SkillWriteBackend)

[OUTPUT]
- run_consolidation_preview: Dry-run consolidation plan
- run_consolidation_execute: Apply consolidation

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
    from myrm_agent_harness.toolkits.retriever.embedding.base import EmbeddingService


async def _get_consolidation_deps() -> tuple[EmbeddingService, BaseChatModel, SkillWriteBackend]:
    """Resolve embedding_service, llm, and write_backend for consolidation.

    Raises HTTPException 503 if dependencies are not configured.
    """
    from fastapi import HTTPException
    from myrm_agent_harness.toolkits.llms import llm_manager
    from myrm_agent_harness.toolkits.retriever.embedding.factory import (
        get_embedding_service,
    )

    from app.core.skills.creation.service import skill_creation_service
    from app.services.agent.platform_config import (
        load_platform_model_config,
        require_platform_embedding_config,
    )

    try:
        embedding_cfg = await require_platform_embedding_config()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Embedding not configured",
        ) from exc

    try:
        platform_model = await load_platform_model_config()
        llm = await llm_manager.get_llm_from_config(platform_model)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="LLM not configured",
        ) from exc

    embedding_service = get_embedding_service(embedding_cfg)
    return embedding_service, llm, skill_creation_service


async def run_consolidation_preview() -> ConsolidationPlan:
    """Run consolidation in dry-run mode and return a ConsolidationPlan."""
    from myrm_agent_harness.agent.skills.curator import SkillCurator
    from myrm_agent_harness.agent.skills.curator.consolidation import ConsolidationPlan

    async with _get_sweep_lock():
        embedding_service, llm, write_backend = await _get_consolidation_deps()
        config = get_curator_config()
        collector = get_stats_collector()

        curator = SkillCurator(
            collector,
            config,
            embedding_service=embedding_service,
            llm=llm,
            write_backend=write_backend,
        )

        scan = await scan_local_skills()
        if not scan.skills:
            return ConsolidationPlan()

        protected_names = await bound_skill_names(scan.skills)
        _, plan = await curator.run_async(
            scan.skills,
            force=True,
            consolidation_dry_run=True,
            protected_names=protected_names,
            installed_names=scan.installed_names,
        )
        if not isinstance(plan, ConsolidationPlan):
            return ConsolidationPlan()

        return plan


async def run_consolidation_execute() -> dict[str, int | str]:
    """Run consolidation and apply changes. Returns structured response."""
    from myrm_agent_harness.agent.skills.curator import SkillCurator
    from myrm_agent_harness.agent.skills.curator.consolidation import (
        ConsolidationReport,
    )

    async with _get_sweep_lock():
        embedding_service, llm, write_backend = await _get_consolidation_deps()
        config = get_curator_config()
        collector = get_stats_collector()

        curator = SkillCurator(
            collector,
            config,
            embedding_service=embedding_service,
            llm=llm,
            write_backend=write_backend,
        )

        scan = await scan_local_skills()
        if not scan.skills:
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_archived": 0,
                "total_created": 0,
                "net_reduction": 0,
                "summary": "No skills available for consolidation.",
            }

        protected_names = await bound_skill_names(scan.skills)
        _, result = await curator.run_async(
            scan.skills,
            force=True,
            consolidation_dry_run=False,
            protected_names=protected_names,
            installed_names=scan.installed_names,
        )

        if result is None or not isinstance(result, ConsolidationReport):
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_archived": 0,
                "total_created": 0,
                "net_reduction": 0,
                "summary": "Consolidation not needed or unavailable.",
            }

    return {
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "total_archived": result.total_archived,
        "total_created": result.total_created,
        "net_reduction": result.net_reduction,
        "summary": result.to_summary(),
    }
