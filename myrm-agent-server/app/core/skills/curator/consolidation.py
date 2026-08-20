"""Consolidation (Umbrella Merge) integration for the curator service.

[INPUT]
- myrm_agent_harness.agent.skills.curator::SkillCurator (POS: Stateless curator engine)
- myrm_agent_harness.agent.skills.curator.consolidation::ConsolidationPlan/ConsolidationReport (POS: Plan/report types)
- app.core.skills.curator.service::_get_sweep_lock, get_curator_config, get_stats_collector (POS: Shared curator state)
- app.core.skills.creation.service::skill_creation_service (POS: SkillWriteBackend)
- app.database.connection::get_session (POS: Agent profile refs rewrite)

[OUTPUT]
- run_consolidation_preview: Dry-run consolidation plan
- run_consolidation_execute: Apply consolidation and rewrite agent skill refs

[POS]
Curator consolidation business service. Shares the sweep lock and curator
config with the main curator service so preview/execute stay mutually
exclusive with background sweeps.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

from .service import _get_sweep_lock, get_curator_config, get_stats_collector

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from myrm_agent_harness.agent.skills.curator.consolidation import (
        ConsolidationPlan,
        ConsolidationReport,
    )
    from myrm_agent_harness.backends.skills.creation_protocols import SkillWriteBackend
    from myrm_agent_harness.backends.skills.types import SkillMetadata
    from myrm_agent_harness.toolkits.retriever.embedding.base import EmbeddingService

logger = logging.getLogger(__name__)


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


async def _load_all_skills() -> list[SkillMetadata]:
    """Load all skills from configured local paths."""
    from myrm_agent_harness.backends.skills.local import LocalSkillBackend

    all_skills: list[SkillMetadata] = []
    for p in DEFAULT_LOCAL_SKILL_PATHS:
        expanded = Path(p).expanduser()
        if not expanded.exists():
            continue
        backend = LocalSkillBackend(expanded, use_snapshot=False)
        all_skills.extend(await backend.list_skills())
    return all_skills


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

        all_skills = await _load_all_skills()
        if not all_skills:
            return ConsolidationPlan()

        _, plan = await curator.run_async(all_skills, force=True, consolidation_dry_run=True)
        if plan is None:
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

        all_skills = await _load_all_skills()
        if not all_skills:
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_archived": 0,
                "total_created": 0,
                "net_reduction": 0,
                "summary": "No skills available for consolidation.",
                "agent_refs_updated": 0,
            }

        _, result = await curator.run_async(all_skills, force=True, consolidation_dry_run=False)

        if result is None or not isinstance(result, ConsolidationReport):
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_archived": 0,
                "total_created": 0,
                "net_reduction": 0,
                "summary": "Consolidation not needed or unavailable.",
                "agent_refs_updated": 0,
            }

    refs_updated = await _rewrite_agent_skill_refs(result)

    return {
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "total_archived": result.total_archived,
        "total_created": result.total_created,
        "net_reduction": result.net_reduction,
        "summary": result.to_summary(),
        "agent_refs_updated": refs_updated,
    }


async def _rewrite_agent_skill_refs(report: ConsolidationReport) -> int:
    """Update agent skill_ids when skills are merged into umbrellas.

    Scans all agent configurations and replaces references to archived
    source skills with the umbrella skill they were merged into.

    Returns the number of agent configurations updated.
    """
    from myrm_agent_harness.agent.skills.curator.consolidation import (
        ConsolidationActionType,
    )

    rename_map: dict[str, str] = {}
    for r in report.results:
        if not r.success:
            continue
        action_type = r.action.action_type
        if action_type in (
            ConsolidationActionType.MERGE,
            ConsolidationActionType.CREATE_UMBRELLA,
        ):
            for source in r.archived_skills:
                rename_map[source] = r.action.target_skill

    if not rename_map:
        return 0

    try:
        from app.database.connection import get_session
        from app.database.repositories.agent_repo import AgentRepository

        updated_count = 0
        async with get_session() as db:
            profiles = await AgentRepository.list_profiles(db)

            for profile in profiles:
                skill_ids = profile.skills or []
                new_skill_ids: list[str] = []
                changed = False

                for sid in skill_ids:
                    if sid in rename_map:
                        replacement = rename_map[sid]
                        if replacement not in new_skill_ids:
                            new_skill_ids.append(replacement)
                        changed = True
                    else:
                        new_skill_ids.append(sid)

                if changed:
                    await AgentRepository.update_profile(db, profile.agent_id, {"skills": new_skill_ids})
                    updated_count += 1
                    logger.info(
                        "Updated agent '%s' skill refs: replaced merged skills",
                        profile.name,
                    )

            await db.commit()

        return updated_count
    except Exception as e:
        logger.warning("Agent skill ref rewrite failed: %s", e)
        return 0
