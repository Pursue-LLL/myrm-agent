"""Curator service — business-layer orchestration for skill lifecycle management.

[INPUT]
- myrm_agent_harness.agent.skills.curator::SkillCurator (POS: Stateless curator engine)
- myrm_agent_harness.backends.skills.forgetting_strategy::CuratorConfig (POS: Curator configuration)
- myrm_agent_harness.backends.skills.stats_collector::SkillStatsCollector (POS: Usage stats collector)
- myrm_agent_harness.backends.skills.local::LocalSkillBackend (POS: Local skill backend)
- app.core.skills.models::DEFAULT_LOCAL_SKILL_PATHS (POS: Skill models and paths)

[OUTPUT]
- get_stats_collector: Shared SkillStatsCollector singleton
- get_curator_config / update_curator_config: Config CRUD with disk persistence
- resolve_skill_path: Skill name to filesystem path resolver
- run_curator_sweep: Execute a curator sweep over all local skills
- get_curator_history: Read past sweep run records
- start_curator_background_task / stop_curator_background_task: Background loop lifecycle

[POS]
Curator business service. Orchestrates skill lifecycle management at the server layer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.agent.skills.curator import CuratorRunResult, SkillCurator
from myrm_agent_harness.backends.skills.forgetting_strategy import CuratorConfig
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector

from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

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

_CURATOR_STATE_FILENAME = "curator_state.json"
_CURATOR_CONFIG_FILENAME = "curator_config.json"
_CURATOR_HISTORY_FILENAME = "curator_history.jsonl"
_HISTORY_MAX_ENTRIES = 30

_stats_collector: SkillStatsCollector | None = None
_curator_config: CuratorConfig | None = None
_background_task: asyncio.Task[None] | None = None
_sweep_lock: asyncio.Lock | None = None


def _get_sweep_lock() -> asyncio.Lock:
    """Lazy-init sweep lock (must be created inside event loop)."""
    global _sweep_lock
    if _sweep_lock is None:
        _sweep_lock = asyncio.Lock()
    return _sweep_lock


def _get_data_dir() -> Path:
    """Get the myrm data directory (~/.myrm)."""
    data_dir = Path.home() / ".myrm"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _get_skills_root() -> Path:
    """Get the primary skills directory."""
    for p in DEFAULT_LOCAL_SKILL_PATHS:
        expanded = Path(p).expanduser()
        if expanded.exists():
            return expanded
    default = Path(DEFAULT_LOCAL_SKILL_PATHS[0]).expanduser()
    default.mkdir(parents=True, exist_ok=True)
    return default


def get_stats_collector() -> SkillStatsCollector:
    """Get or create the shared SkillStatsCollector."""
    global _stats_collector
    if _stats_collector is None:
        _stats_collector = SkillStatsCollector(_get_skills_root())
    return _stats_collector


def get_curator_config() -> CuratorConfig:
    """Load curator config from disk or return defaults."""
    global _curator_config
    if _curator_config is not None:
        return _curator_config

    config_path = _get_data_dir() / _CURATOR_CONFIG_FILENAME
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            _curator_config = CuratorConfig.from_dict(data)
        except Exception as e:
            logger.warning("Failed to load curator config: %s, using defaults", e)
            _curator_config = CuratorConfig()
    else:
        _curator_config = CuratorConfig()

    return _curator_config


def update_curator_config(updates: dict[str, object]) -> CuratorConfig:
    """Update curator config with partial updates and persist."""
    global _curator_config
    current = get_curator_config()
    current_dict = current.to_dict()
    current_dict.update(updates)
    _curator_config = CuratorConfig.from_dict(current_dict)

    config_path = _get_data_dir() / _CURATOR_CONFIG_FILENAME
    config_path.write_text(json.dumps(_curator_config.to_dict(), indent=2))

    return _curator_config


def resolve_skill_path(skill_name: str) -> Path | None:
    """Resolve a skill name to its directory path across all configured paths."""
    for p in DEFAULT_LOCAL_SKILL_PATHS:
        expanded = Path(p).expanduser()
        candidate = expanded / skill_name
        if candidate.is_dir():
            return candidate
    return None


async def run_curator_sweep(*, force: bool = False, trigger: Literal["manual", "background"] = "background") -> CuratorRunResult:
    """Execute a curator sweep over all configured local skill paths.

    Uses an asyncio lock to prevent concurrent sweeps from the background
    loop and manual API trigger.

    Args:
        force: If True, bypass the enabled check (for manual API triggers).
        trigger: Source of this sweep — "manual" (API) or "background" (loop).
    """
    from myrm_agent_harness.backends.skills.local import LocalSkillBackend

    async with _get_sweep_lock():
        config = get_curator_config()
        collector = get_stats_collector()
        curator = SkillCurator(collector, config)

        all_skills = []
        for p in DEFAULT_LOCAL_SKILL_PATHS:
            expanded = Path(p).expanduser()
            if not expanded.exists():
                continue
            backend = LocalSkillBackend(expanded, use_snapshot=False)
            all_skills.extend(await backend.list_skills())

        if not all_skills:
            return CuratorRunResult()

        t0 = time.monotonic()
        result = curator.run(all_skills, force=force)
        duration_ms = round((time.monotonic() - t0) * 1000)

        _save_last_run_time()
        _save_history(result, trigger=trigger, duration_ms=duration_ms)

        return result


def _save_history(
    result: CuratorRunResult,
    *,
    trigger: Literal["manual", "background"],
    duration_ms: int,
) -> None:
    """Append a sweep result to the history JSONL file, keeping at most _HISTORY_MAX_ENTRIES."""
    history_path = _get_data_dir() / _CURATOR_HISTORY_FILENAME

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "trigger": trigger,
        "duration_ms": duration_ms,
        "skills_scanned": result.skills_scanned,
        "total_transitions": result.total_transitions,
        "stale_count": result.stale_count,
        "archived_count": result.archived_count,
        "skipped_pinned": result.skipped_pinned,
        "transitions": [
            {
                "skill_name": t.skill_name,
                "from_status": t.from_status,
                "to_status": t.to_status,
                "reason": t.reason_type,
            }
            for t in result.transitions
        ],
        "errors": result.errors,
    }

    lines: list[str] = []
    if history_path.exists():
        try:
            lines = [ln for ln in history_path.read_text().splitlines() if ln.strip()]
        except Exception:
            lines = []

    lines.append(json.dumps(entry, ensure_ascii=False))

    if len(lines) > _HISTORY_MAX_ENTRIES:
        lines = lines[-_HISTORY_MAX_ENTRIES:]

    history_path.write_text("\n".join(lines) + "\n")


def get_curator_history(limit: int = 10) -> list[dict[str, object]]:
    """Read the most recent curator run records.

    Args:
        limit: Maximum number of entries to return (newest first).
    """
    if limit <= 0:
        return []

    history_path = _get_data_dir() / _CURATOR_HISTORY_FILENAME
    if not history_path.exists():
        return []

    try:
        lines = [ln for ln in history_path.read_text().splitlines() if ln.strip()]
    except Exception:
        return []

    entries: list[dict[str, object]] = []
    for ln in reversed(lines):
        try:
            entries.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
        if len(entries) >= limit:
            break

    return entries


def _save_last_run_time() -> None:
    """Persist the timestamp of the last curator run."""
    state_path = _get_data_dir() / _CURATOR_STATE_FILENAME
    state_path.write_text(json.dumps({"last_run_at": datetime.now(UTC).isoformat()}))


def _get_last_run_time() -> datetime | None:
    """Get the timestamp of the last curator run."""
    state_path = _get_data_dir() / _CURATOR_STATE_FILENAME
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text())
        return datetime.fromisoformat(data["last_run_at"])
    except Exception:
        return None


async def _curator_background_loop() -> None:
    """Background loop that runs curator sweeps at configured intervals."""
    while True:
        try:
            config = get_curator_config()
            if not config.enabled:
                await asyncio.sleep(3600)
                continue

            last_run = _get_last_run_time()
            interval_seconds = config.interval_hours * 3600

            if last_run is not None:
                elapsed = (datetime.now(UTC) - last_run).total_seconds()
                if elapsed < interval_seconds:
                    wait_time = interval_seconds - elapsed
                    await asyncio.sleep(min(wait_time, 3600))
                    continue

            result = await run_curator_sweep(trigger="background")
            if result.total_transitions > 0:
                logger.info(
                    "Curator background sweep: %d transitions (%d stale, %d archived)",
                    result.total_transitions,
                    result.stale_count,
                    result.archived_count,
                )

            await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Curator background error: %s", e)
            await asyncio.sleep(3600)


def start_curator_background_task() -> None:
    """Start the curator background task (call at app startup)."""
    global _background_task
    if _background_task is not None and not _background_task.done():
        return
    _background_task = asyncio.create_task(_curator_background_loop())
    logger.info("Curator background task started")


def stop_curator_background_task() -> None:
    """Stop the curator background task (call at app shutdown)."""
    global _background_task
    if _background_task is not None and not _background_task.done():
        _background_task.cancel()
        _background_task = None


# ---------------------------------------------------------------------------
# Consolidation (Umbrella Merge) integration
# ---------------------------------------------------------------------------


async def _get_consolidation_deps() -> tuple[EmbeddingService, BaseChatModel, SkillWriteBackend]:
    """Resolve embedding_service, llm, and write_backend for consolidation.

    Raises HTTPException 503 if dependencies are not configured.
    """
    from fastapi import HTTPException
    from myrm_agent_harness.toolkits.llms import llm_manager
    from myrm_agent_harness.toolkits.retriever.embedding.factory import get_embedding_service

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
            detail=f"Embedding not configured: {exc}",
        ) from exc

    try:
        platform_model = await load_platform_model_config()
        llm = await llm_manager.get_llm_from_config(platform_model)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LLM not configured: {exc}",
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
