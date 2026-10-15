"""Curator service — business-layer orchestration for skill lifecycle management.

[INPUT]
- myrm_agent_harness.agent.skills.curator::SkillCurator (POS: Stateless curator engine)
- myrm_agent_harness.backends.skills.curator_config::CuratorConfig (POS: Curator configuration with construction-time range validation)
- myrm_agent_harness.backends.skills.stats_collector::SkillStatsCollector (POS: Usage stats collector)
- myrm_agent_harness.backends.skills.local::LocalSkillBackend (POS: Local skill backend)
- app.core.skills.models::DEFAULT_LOCAL_SKILL_PATHS (POS: Skill models and paths)
- app.core.skills.config_version::bump_skill_config_version (POS: Skill config version bumper; invalidates warm-chat agents)
- app.core.skills.curator.bound_skills::bound_skill_names (POS: Skills bound by agent profiles / cron jobs)

[OUTPUT]
- get_stats_collector: Shared SkillStatsCollector singleton
- get_curator_config / update_curator_config: Config CRUD with disk persistence
- resolve_skill_path: Skill name to filesystem path resolver
- apply_skill_archived / set_skill_archived: Archive/restore a skill's lifecycle (single write path for user-initiated archive)
- describe_skill_lifecycle: Read a skill's archive/pinned state for UI surfaces
- SkillNotFoundError / SkillPinnedError: Domain errors raised by set_skill_archived
- run_curator_sweep: Execute a curator sweep over all local skills (skills bound by agents / cron jobs are exempt)
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
from typing import Literal

from myrm_agent_harness.agent.skills.curator import CuratorRunResult, SkillCurator
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
from myrm_agent_harness.backends.skills.forgetting_strategy import evaluate_skill_health_findings
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus

from app.core.skills.config_version import bump_skill_config_version
from app.core.skills.curator.bound_skills import bound_skill_names
from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

logger = logging.getLogger(__name__)

_CURATOR_STATE_FILENAME = "curator_state.json"
_CURATOR_CONFIG_FILENAME = "curator_config.json"
_CURATOR_HISTORY_FILENAME = "curator_history.jsonl"
_HISTORY_MAX_ENTRIES = 30
_REMEDIATION_ACTIONS = frozenset({"unpin_and_archive", "archive", "reset_stats"})

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


def get_stats_collector() -> SkillStatsCollector:
    """Get or create the shared SkillStatsCollector."""
    global _stats_collector
    if _stats_collector is None:
        _stats_collector = SkillStatsCollector()
        from myrm_agent_harness.backends.skills.usage_recorder import (
            set_stats_collector,
        )

        set_stats_collector(_stats_collector)
    return _stats_collector


def _load_curator_config(config_path: Path) -> CuratorConfig:
    """Read the stored config; an unreadable or out-of-range file falls back to defaults.

    The master switch is the one value that survives a bad threshold: resetting it would
    switch on a curator the user had turned off.
    """
    try:
        data = json.loads(config_path.read_text())
    except Exception as e:
        logger.warning("Failed to read curator config: %s, using defaults", e)
        return CuratorConfig()
    try:
        return CuratorConfig.from_dict(data)
    except Exception as e:
        logger.warning("Invalid curator config: %s, using default thresholds", e)
        enabled = data.get("enabled", True) if isinstance(data, dict) else True
        return CuratorConfig(enabled=bool(enabled))


def get_curator_config() -> CuratorConfig:
    """Load curator config from disk or return defaults."""
    global _curator_config
    if _curator_config is not None:
        return _curator_config

    config_path = _get_data_dir() / _CURATOR_CONFIG_FILENAME
    _curator_config = _load_curator_config(config_path) if config_path.exists() else CuratorConfig()
    return _curator_config


def update_curator_config(updates: dict[str, object]) -> CuratorConfig:
    """Update curator config with partial updates and persist.

    Raises:
        ValueError: A merged value is outside the range ``CuratorConfig`` accepts; the
            cached and the stored config are left untouched.
    """
    global _curator_config
    current = get_curator_config()
    current_dict = current.to_dict()
    current_dict.update(updates)
    _curator_config = CuratorConfig.from_dict(current_dict)

    config_path = _get_data_dir() / _CURATOR_CONFIG_FILENAME
    config_path.write_text(json.dumps(_curator_config.to_dict(), indent=2))

    return _curator_config


def resolve_skill_path(skill_name: str) -> Path | None:
    """Resolve a skill name to its directory path across all configured paths.

    Names that are not a single plain path segment never resolve, so a request can not
    address a directory outside the skill roots.
    """
    if skill_name in ("", ".", "..") or "/" in skill_name or "\\" in skill_name:
        return None
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

        protected_names = await bound_skill_names(all_skills)

        t0 = time.monotonic()
        result = curator.run(all_skills, force=force, protected_names=protected_names)
        duration_ms = round((time.monotonic() - t0) * 1000)

        _save_last_run_time()
        _save_history(result, trigger=trigger, duration_ms=duration_ms)
        if result.archived_count:
            bump_skill_config_version()

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


async def get_skill_diagnostics() -> dict[str, object]:
    """Evaluate full skill library health and return structured Doctor Findings."""
    from myrm_agent_harness.backends.skills.local import LocalSkillBackend

    config = get_curator_config()
    all_skills = []
    for p in DEFAULT_LOCAL_SKILL_PATHS:
        expanded = Path(p).expanduser()
        if not expanded.exists():
            continue
        backend = LocalSkillBackend(expanded, use_snapshot=False)
        all_skills.extend(await backend.list_skills())

    diagnosis = evaluate_skill_health_findings(all_skills, config)
    return diagnosis.to_dict()


class SkillNotFoundError(LookupError):
    """Raised when a skill name cannot be resolved to a local skill directory."""


class SkillPinnedError(RuntimeError):
    """Raised when archiving a pinned skill (the user must unpin it first)."""


def describe_skill_lifecycle(skill_name: str) -> tuple[bool, bool] | None:
    """Return ``(archived, pinned)`` for a local skill, or ``None`` when it is not a manageable local skill."""
    skill_path = resolve_skill_path(skill_name)
    if skill_path is None:
        return None
    stats = get_stats_collector().get_stats(skill_path)
    return stats.lifecycle_status == SkillLifecycleStatus.ARCHIVED, bool(stats.pinned)


def apply_skill_archived(collector: SkillStatsCollector, skill_path: Path, *, archived: bool) -> SkillLifecycleStatus:
    """Write the archive/restore lifecycle state, refusing to archive a pinned skill.

    Single write path for user-initiated archive/restore so every surface (curator API,
    learning timeline) honours the same pinned guard and writes the state the skill loader reads.
    The skill config version is bumped because warm chats reuse their built agent until the
    execution fingerprint (which includes that version) changes; without it the skill stays
    loaded in the running chat.
    """
    if archived and collector.get_stats(skill_path).pinned:
        raise SkillPinnedError(skill_path.name)

    status = SkillLifecycleStatus.ARCHIVED if archived else SkillLifecycleStatus.ACTIVE
    collector.update_lifecycle_status(skill_path, status)
    bump_skill_config_version()
    return status


def set_skill_archived(skill_name: str, *, archived: bool) -> SkillLifecycleStatus:
    """Resolve ``skill_name`` to a local skill and archive/restore it."""
    skill_path = resolve_skill_path(skill_name)
    if skill_path is None:
        raise SkillNotFoundError(skill_name)
    return apply_skill_archived(get_stats_collector(), skill_path, archived=archived)


async def remediate_skill_finding(skill_name: str, action: str) -> dict[str, object]:
    """Execute remediation action for a diagnosed skill finding.

    Supported actions:
    - 'unpin_and_archive': Unpin the skill and transition lifecycle status to ARCHIVED.
    - 'archive': Transition lifecycle status to ARCHIVED (refused while the skill is pinned).
    - 'reset_stats': Discard the usage counters and history so the success rate starts a fresh window.
    """
    if action not in _REMEDIATION_ACTIONS:
        return {"success": False, "error": f"Unsupported remediation action: {action}"}

    skill_dir = resolve_skill_path(skill_name)
    if skill_dir is None:
        return {"success": False, "error": f"Skill '{skill_name}' directory not found"}

    collector = get_stats_collector()
    if action == "reset_stats":
        collector.reset_usage(skill_dir)
    else:
        if action == "unpin_and_archive":
            collector.set_pinned(skill_dir, pinned=False)
        try:
            apply_skill_archived(collector, skill_dir, archived=True)
        except SkillPinnedError:
            return {"success": False, "error": f"Skill '{skill_name}' is pinned; unpin it first"}

    stats = collector.get_stats(skill_dir)
    return {
        "success": True,
        "skill_name": skill_name,
        "action": action,
        "new_status": SkillLifecycleStatus(stats.lifecycle_status).value,
        "pinned": stats.pinned,
        "call_count": stats.call_count,
    }
