"""Seed layout and the record of the last complete prebuilt sync.

[INPUT]
myrm_agent_harness.agent.skills.market.sanitizer::SKILL_MD_FILE (POS: SKILL.md file name)
myrm_agent_harness.toolkits.storage.base::StorageProvider (POS: unified storage abstraction)
app.core.storage.paths (POS: skill storage keys)

[OUTPUT]
iter_seed_dirs, iter_bundle_files: which seed directories and bundle files the sync handles
seeds_fingerprint: digest of everything the sync reads from the seeds
load_reusable_skill_ids, save_sync_state: the record of the last complete sync, kept beside the stored copies

[POS]
Lets a start whose seeds equal those of the last complete sync, and whose stored copies are all present, skip the
reconciliation before the server listens: the stored skills are exactly what that reconciliation would leave.
The record sits under the prebuilt skills prefix, so it moves, is restored and is wiped together with the copies it
describes, and the skill listings (which read ``_metadata.json`` files and skill directories) never see it.
It is only a hint: the reconciliation runs in full after the first screen, so a record that is wrong costs seconds of
stale snapshots, not lasting damage.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.toolkits.storage.base import StorageProvider

from app.core.storage.paths import (
    get_skill_file_path,
    get_skill_metadata_path,
    get_skills_type_prefix,
)
from app.core.storage.types import SkillType

logger = logging.getLogger(__name__)

# Bump when the record's shape, the completeness rule or what a reconciliation writes changes: a record of an older
# format never matches, so the next start reconciles in full before it listens.
_STATE_FORMAT = 1
_STATE_KEY = f"{get_skills_type_prefix(SkillType.PREBUILT)}.seed-sync-state.json"


def iter_seed_dirs(seeds_dir: Path) -> Iterator[Path]:
    """Seed directories in a stable order: those with a SKILL.md whose name does not start with ``_`` or ``.``."""
    for skill_dir in sorted(seeds_dir.iterdir()):
        if skill_dir.is_dir() and not skill_dir.name.startswith(("_", ".")) and (skill_dir / SKILL_MD_FILE).is_file():
            yield skill_dir


def iter_bundle_files(skill_dir: Path) -> Iterator[tuple[Path, str]]:
    """Files bundled next to a seed's SKILL.md (scripts, references, assets) with their POSIX path inside the seed."""
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_dir)
        if relative.name == SKILL_MD_FILE or relative.name.startswith("."):
            continue
        if any(part.startswith("_") for part in relative.parts):
            continue
        yield path, relative.as_posix()


def seeds_fingerprint(seeds_dir: Path) -> str:
    """Digest of every seed's name, SKILL.md and bundle files: everything a sync reads from the seeds.

    Blocking file reads (about 1 MB for the shipped seeds); callers on the event loop run it in a thread.
    """
    digest = hashlib.sha256()

    def feed(data: bytes) -> None:
        # Length-prefixed, so that no two different seed sets concatenate to the same byte stream.
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)

    feed(str(_STATE_FORMAT).encode())
    for skill_dir in iter_seed_dirs(seeds_dir):
        feed(skill_dir.name.encode())
        for path, relative in ((skill_dir / SKILL_MD_FILE, SKILL_MD_FILE), *iter_bundle_files(skill_dir)):
            feed(relative.encode())
            feed(path.read_bytes())
    return digest.hexdigest()


async def _read_state(storage: StorageProvider) -> str | None:
    """The stored record, or None when there is none or it is not text."""
    try:
        return await storage.read_text(_STATE_KEY)
    except (FileNotFoundError, ValueError):
        return None


async def load_reusable_skill_ids(storage: StorageProvider, fingerprint: str) -> tuple[str, ...] | None:
    """Skill ids of the last complete sync if its seeds equal ``fingerprint`` and every stored copy is still present.

    Presence means the SKILL.md and the ``_metadata.json`` snapshot of each skill, the two files the skill listings read.
    Anything else (no record, an unreadable or older record, other seeds, a missing file, a failed listing) is None,
    and the caller reconciles in full as it always did.
    """
    text = await _read_state(storage)
    if text is None:
        return None
    try:
        record = json.loads(text)
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("format") != _STATE_FORMAT or record.get("fingerprint") != fingerprint:
        return None
    skill_ids = record.get("skill_ids")
    if not isinstance(skill_ids, list) or not skill_ids or not all(isinstance(skill_id, str) for skill_id in skill_ids):
        return None

    try:
        stored = set(await storage.list(get_skills_type_prefix(SkillType.PREBUILT)))
    except Exception as exc:
        logger.warning("Failed to list prebuilt skills, reconciling in full: %s", exc)
        return None
    for skill_id in skill_ids:
        if (
            get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE) not in stored
            or get_skill_metadata_path(SkillType.PREBUILT, skill_id) not in stored
        ):
            return None
    return tuple(skill_ids)


async def save_sync_state(storage: StorageProvider, fingerprint: str, skill_ids: tuple[str, ...]) -> None:
    """Record that a sync of the seeds ``fingerprint`` completed; call it only after the sync has finished.

    The record is an optimization, so a failure to write it is logged and the next start simply reconciles in full.
    """
    payload = json.dumps({"format": _STATE_FORMAT, "fingerprint": fingerprint, "skill_ids": list(skill_ids)})
    try:
        if await _read_state(storage) != payload:
            await storage.write_text(_STATE_KEY, payload)
    except Exception as exc:
        logger.warning("Failed to record the prebuilt skill sync state: %s", exc)
