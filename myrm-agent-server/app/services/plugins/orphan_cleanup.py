"""Startup repair of plugin skill records that have no skill files (business layer).

A record with ``path == "plugins/<plugin>/<skill>/SKILL.md"`` and
``created_by == "plugin_import"`` lives only in the evolution database: no skill directory
exists for it, so it can never load. It still counts against the evolution budget and
experts keep bound ids that resolve to nothing. Plugin skills are installed as real
skills, so such a record has no owner and is removed.

[INPUT]
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: skills.db access.)
- app.core.skills.store.service::skills_service (POS: the installed-skill catalog.)
- app.services.agent.agent_service::AgentService (POS: expert listing and binding updates.)
- app.config.settings::settings (POS: state directory for the backup file.)

[OUTPUT]
- OrphanCleanupReport: what one sweep removed.
- sweep_orphan_plugin_skill_records: idempotent sweep (a clean store is a no-op).

[POS]
Startup repair. Every removed record is appended to a JSONL backup first, deletion goes
through ``SkillStore.delete_skill`` (never raw SQL), and a record whose id resolves to an
installed skill is left alone, so a real skill is never touched.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord

__all__ = ["OrphanCleanupReport", "sweep_orphan_plugin_skill_records"]

logger = logging.getLogger(__name__)

_IMPORT_CREATOR = "plugin_import"
_IMPORT_PATH_PREFIX = "plugins/"
_BACKUP_FILENAME = "orphan_plugin_skill_records.jsonl"
_PAGE_SIZE = 200


@dataclass(frozen=True)
class OrphanCleanupReport:
    removed_records: int = 0
    cleaned_bindings: int = 0  # expert bindings dropped because they pointed at a removed record
    backup_path: Path | None = None


async def sweep_orphan_plugin_skill_records() -> OrphanCleanupReport:
    """Remove orphaned plugin skill records and the expert bindings that point at them.

    Nothing is deleted when the installed-skill catalog cannot be read or the backup
    cannot be written: with no proof that a record is dead, it is kept.
    """
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    store = get_evolution_skill_store()
    active = await asyncio.to_thread(store.get_active_skills)
    candidates = [record for record in active if _is_orphan_candidate(record)]
    if not candidates:
        return OrphanCleanupReport()

    installed_ids = await _installed_skill_ids()
    dead = [record for record in candidates if record.skill_id not in installed_ids]
    if not dead:
        return OrphanCleanupReport()

    backup_path = await asyncio.to_thread(_append_backup, dead)
    removed: set[str] = set()
    for record in dead:
        try:
            await store.delete_skill(record.skill_id)
        except Exception as exc:
            logger.warning("Orphan plugin skill record %s could not be removed: %s", record.skill_id, exc)
            continue
        removed.add(record.skill_id)

    cleaned = await _unbind_from_experts(removed)
    logger.info(
        "Orphan plugin skill cleanup: removed %d record(s), dropped %d expert binding(s); backup %s",
        len(removed),
        cleaned,
        backup_path,
    )
    return OrphanCleanupReport(removed_records=len(removed), cleaned_bindings=cleaned, backup_path=backup_path)


def _is_orphan_candidate(record: SkillRecord) -> bool:
    return record.lineage.created_by == _IMPORT_CREATOR and record.path.startswith(_IMPORT_PATH_PREFIX)


async def _installed_skill_ids() -> frozenset[str]:
    from app.core.skills.store.service import skills_service

    return frozenset(skill.id for skill in await skills_service.list_skills())


def _append_backup(records: list[SkillRecord]) -> Path:
    from app.config.settings import settings

    path = Path(settings.database.state_dir) / _BACKUP_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as backup:
        for record in records:
            backup.write(json.dumps({"backed_up_at": stamp, "record": record.to_dict()}, ensure_ascii=False) + "\n")
        backup.flush()
    return path


async def _unbind_from_experts(removed_ids: set[str]) -> int:
    """Drop bindings to ``removed_ids`` from every expert; returns how many bindings were dropped."""
    if not removed_ids:
        return 0

    from app.database.dto import AgentUpdate
    from app.services.agent.agent_service import AgentService

    dropped = 0
    page = 1
    while True:
        profiles, total = await AgentService.get_agent_list(page=page, page_size=_PAGE_SIZE)
        for profile in profiles:
            bound = list(profile.skills or [])
            kept = [skill_id for skill_id in bound if skill_id not in removed_ids]
            if len(kept) == len(bound):
                continue
            try:
                await AgentService.update_agent(profile.id, AgentUpdate.model_validate({"skill_ids": kept}))
            except Exception as exc:
                logger.warning("Expert %s kept a dangling skill binding: %s", profile.id, exc)
                continue
            dropped += len(bound) - len(kept)
        if page * _PAGE_SIZE >= total:
            return dropped
        page += 1
