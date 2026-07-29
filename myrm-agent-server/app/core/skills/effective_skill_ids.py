"""Resolve Agent runtime skill IDs from profile and user catalog.

[INPUT]
- myrm_agent_harness.backends.skills.local_skill_id::local_skill_id_from_path (POS: Canonical path-hash local skill ID)
- app.core.skills.store.service::skills_service (POS: Skill CRUD and user config)

[OUTPUT]
- is_canonical_local_skill_id: Check whether a skill ID uses the path-hash local format
- normalize_local_skill_id: Map legacy local::{name} IDs to canonical IDs
- migrate_legacy_local_skill_ids: Persist migrated enabled local skill IDs
- resolve_runtime_skill_ids: Agent explicit allowlist or fallback to all user-enabled skills

[POS]
Runtime skill ID resolver. Closes the gap between user-enabled catalog and Agent
SkillAgent preload when the Agent profile has an empty skill allowlist.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path

from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

_LOCAL_INSTALL_DIR = Path("~/.myrm/skills").expanduser()


def is_canonical_local_skill_id(skill_id: str) -> bool:
    if not skill_id.startswith("local::"):
        return False
    suffix = skill_id.removeprefix("local::")
    if len(suffix) != 16:
        return False
    try:
        int(suffix, 16)
    except ValueError:
        return False
    return True


def normalize_local_skill_id(
    skill_id: str,
    install_roots: list[Path] | None = None,
) -> str:
    """Map legacy local::{name} IDs to canonical path-hash IDs when possible."""
    if is_canonical_local_skill_id(skill_id) or not skill_id.startswith("local::"):
        return skill_id

    legacy_name = skill_id.removeprefix("local::")
    roots = install_roots if install_roots is not None else [_LOCAL_INSTALL_DIR]
    for root in roots:
        candidate = root / legacy_name
        if candidate.is_dir():
            return local_skill_id_from_path(candidate)
    return skill_id


def _legacy_install_roots(local_skill_paths: list[str]) -> list[Path]:
    roots = [_LOCAL_INSTALL_DIR]
    for path_str in local_skill_paths:
        expanded = Path(path_str).expanduser()
        if expanded not in roots:
            roots.append(expanded)
    return roots


def _has_legacy_local_ids(skill_ids: list[str]) -> bool:
    return any(
        sid.startswith("local::") and not is_canonical_local_skill_id(sid)
        for sid in skill_ids
    )


async def migrate_legacy_local_skill_ids() -> list[str]:
    """Normalize enabled local skill IDs and persist when legacy name IDs are found."""
    config = await skills_service.user_config.get_config()
    if not _has_legacy_local_ids(config.enabled_local_skill_ids):
        return list(config.enabled_local_skill_ids)

    normalized: list[str] = []
    changed = False
    install_roots = _legacy_install_roots(config.local_skill_paths)

    for skill_id in config.enabled_local_skill_ids:
        canonical = normalize_local_skill_id(skill_id, install_roots)
        if canonical != skill_id:
            changed = True
            logger.info("Migrated legacy local skill id %s -> %s", skill_id, canonical)
        if canonical not in normalized:
            normalized.append(canonical)

    if changed:
        config.enabled_local_skill_ids = normalized
        await skills_service.user_config.save_config(config)

    return normalized


async def resolve_runtime_skill_ids(profile_skill_ids: list[str] | None) -> list[str]:
    """Return explicit Agent allowlist, or all user-enabled skills when empty."""
    config = await skills_service.user_config.get_config()
    install_roots = _legacy_install_roots(config.local_skill_paths)
    explicit = [
        normalize_local_skill_id(sid.strip(), install_roots)
        for sid in (profile_skill_ids or [])
        if sid.strip()
    ]
    if explicit:
        return explicit

    local_ids = (
        await migrate_legacy_local_skill_ids()
        if _has_legacy_local_ids(config.enabled_local_skill_ids)
        else list(config.enabled_local_skill_ids)
    )
    seen: set[str] = set()
    resolved: list[str] = []
    for skill_id in [*config.enabled_prebuilt_ids, *local_ids]:
        if skill_id in seen:
            continue
        seen.add(skill_id)
        resolved.append(skill_id)
    return resolved

