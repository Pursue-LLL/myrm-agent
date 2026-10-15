"""Persist last replace rollback batch id on skills.

[INPUT]
- app.core.skills.models::Skill, SkillType (POS: skill records)
- app.core.skills.store.service::skills_service (POS: metadata IO)

[OUTPUT]
- get_last_replace_batch_id / set_last_replace_batch_id / clear_last_replace_batch_id

[POS]
Skill Change Contract undo pointer. Local skills use .replace_state.json sidecar.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from myrm_agent_harness.toolkits.storage.paths import SKILL_METADATA_FILE

from app.core.skills.models import Skill, SkillType

logger = logging.getLogger(__name__)

_REPLACE_STATE_FILE = ".replace_state.json"


def _read_local_replace_state(skill_dir: Path) -> dict[str, object]:
    path = skill_dir / _REPLACE_STATE_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return {}


def _write_local_replace_state(skill_dir: Path, batch_id: str | None) -> None:
    path = skill_dir / _REPLACE_STATE_FILE
    if not batch_id:
        if path.is_file():
            path.unlink(missing_ok=True)
        return
    path.write_text(
        json.dumps({"last_replace_batch_id": batch_id}, indent=2),
        encoding="utf-8",
    )


async def get_last_replace_batch_id(skill: Skill) -> str | None:
    if skill.last_replace_batch_id:
        return skill.last_replace_batch_id
    if skill.type == SkillType.LOCAL:
        state = _read_local_replace_state(Path(skill.storage_path))
        raw = state.get("last_replace_batch_id")
        return raw if isinstance(raw, str) and raw.strip() else None
    return None


async def set_last_replace_batch_id(skill_id: str, batch_id: str) -> None:
    from app.core.skills.store.service import skills_service

    skill = await skills_service.get_skill(skill_id)
    if not skill:
        logger.warning("set_last_replace_batch_id: skill not found %s", skill_id)
        return

    if skill.type == SkillType.LOCAL:
        _write_local_replace_state(Path(skill.storage_path), batch_id)
        return

    updated = replace(
        skill,
        last_replace_batch_id=batch_id,
        updated_at=datetime.utcnow(),
    )
    metadata_path = f"{updated.storage_path}/{SKILL_METADATA_FILE}"
    await skills_service.storage.write_text(metadata_path, json.dumps(updated.to_dict(), indent=2))


async def clear_last_replace_batch_id(skill_id: str) -> None:
    from app.core.skills.store.service import skills_service

    skill = await skills_service.get_skill(skill_id)
    if not skill:
        return
    if skill.type == SkillType.LOCAL:
        _write_local_replace_state(Path(skill.storage_path), None)
        return
    updated = replace(
        skill,
        last_replace_batch_id=None,
        updated_at=datetime.utcnow(),
    )
    metadata_path = f"{updated.storage_path}/{SKILL_METADATA_FILE}"
    await skills_service.storage.write_text(metadata_path, json.dumps(updated.to_dict(), indent=2))
