"""Write approved competitor skill bundles into the local skills directory.

[INPUT]
app.core.skills.models::DEFAULT_LOCAL_SKILL_PATHS (POS: local skill roots, first entry is the primary root)

[OUTPUT]
apply_skill_migration: write each bundle's SKILL.md (backing up the replaced file) and seed its usage ledger
build_stats_json: map a Hermes .usage.json record to the .stats.json ledger format

[POS]
Apply step of the skill migration review queue; the approve route in app.api.skills.migrations delegates here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

_USAGE_LEDGER_FILENAME = ".stats.json"

_HERMES_LIFECYCLE_STATES = {"active": "active", "stale": "stale", "archived": "archived"}


async def apply_skill_migration(skills_raw: list[object]) -> dict[str, int]:
    """Write competitor skill bundles into the primary local skills directory."""
    # Resolved per call: the skills root is runtime-configurable.
    from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS

    base = Path(DEFAULT_LOCAL_SKILL_PATHS[0]).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    imported = 0
    overwritten = 0
    usage_preserved = 0

    for item in skills_raw:
        if not isinstance(item, dict):
            continue
        name_raw = item.get("name")
        content_raw = item.get("content")
        if not isinstance(name_raw, str) or not isinstance(content_raw, str):
            continue
        name = name_raw.strip()
        content = content_raw.strip()
        if not name or not content:
            continue
        skill_dir = base / name
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
            shutil.copy2(skill_md, skill_md.with_name(f"{skill_md.name}.bak-migration"))
            overwritten += 1
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(content, encoding="utf-8")
        imported += 1

        if _seed_usage_ledger(skill_dir, item.get("usage_stats")):
            usage_preserved += 1

    result: dict[str, int] = {
        "skills_imported": imported,
        "skills_overwritten": overwritten,
    }
    if usage_preserved:
        result["usage_preserved"] = usage_preserved
    return result


def _seed_usage_ledger(skill_dir: Path, usage_stats: object) -> bool:
    """Seed the ledger of a migrated skill from its Hermes usage record; return whether one was written.

    An existing ledger holds the run evidence gathered here (outcomes, history, pinned) and is never replaced,
    matching how a batch import carries the ledger of a replaced skill over.
    """
    ledger = skill_dir / _USAGE_LEDGER_FILENAME
    if ledger.is_file() or not isinstance(usage_stats, dict):
        return False
    stats_json = build_stats_json(usage_stats)
    if stats_json is None:
        return False
    ledger.write_text(json.dumps(stats_json, indent=2), encoding="utf-8")
    return True


def build_stats_json(hermes_usage: dict[str, object]) -> dict[str, object] | None:
    """Map a Hermes .usage.json record to the Myrm .stats.json format.

    Mapping: use_count→call_count, last_used_at→last_used_at,
    created_at→created_at, state→lifecycle_status, pinned→pinned.
    Hermes records no run outcomes, so the success/failure counters stay empty instead of inventing evidence.
    """
    call_count = hermes_usage.get("use_count", 0)
    if not isinstance(call_count, int):
        try:
            call_count = int(call_count)
        except (TypeError, ValueError):
            call_count = 0

    last_used_at = hermes_usage.get("last_used_at")
    created_at = hermes_usage.get("created_at")
    state = hermes_usage.get("state", "active")
    pinned = bool(hermes_usage.get("pinned", False))

    lifecycle_status = _HERMES_LIFECYCLE_STATES.get(str(state), "active")

    if call_count == 0 and not last_used_at and not created_at:
        return None

    return {
        "call_count": call_count,
        "success_count": 0,
        "failure_count": 0,
        "last_used_at": last_used_at if isinstance(last_used_at, str) else None,
        "lifecycle_status": lifecycle_status,
        "pinned": pinned,
        "merged_into": None,
        "created_at": created_at if isinstance(created_at, str) else None,
    }
