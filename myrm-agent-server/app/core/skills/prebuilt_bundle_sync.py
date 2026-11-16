"""Copy a prebuilt seed's bundled files (scripts, references, assets) into storage.

[INPUT]
myrm_agent_harness.toolkits.storage.base::StorageProvider (POS: unified storage abstraction)
app.core.skills.prebuilt_sync_state::iter_bundle_files (POS: which files of a seed are bundle files)
app.core.storage.paths::get_skill_file_path (POS: skill storage keys)

[OUTPUT]
sync_skill_bundle_files: write the bundle files of one seed that storage does not already hold

[POS]
Bundle files always follow the upstream seeds and sit outside the SKILL.md three-way hash protection: users edit
prose, not bundled tooling. The sync reruns on every start, so a file that already matches is left alone; rewriting
about a megabyte of identical files each time is disk work for nothing, and file churn that real-time scanners inspect.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.storage.base import StorageProvider

from app.core.skills.prebuilt_sync_state import iter_bundle_files
from app.core.storage.paths import get_skill_file_path
from app.core.storage.types import SkillType

# Written as UTF-8 text; every other bundle file is copied byte for byte.
_TEXT_BUNDLE_SUFFIXES = frozenset({".py", ".md", ".txt", ".json", ".yaml", ".yml", ".sh"})


async def _stored_matches(storage: StorageProvider, key: str, content: bytes) -> bool:
    """Whether storage already holds exactly ``content`` at ``key``."""
    try:
        return await storage.read(key) == content
    except FileNotFoundError:
        return False


async def sync_skill_bundle_files(storage: StorageProvider, skill_id: str, skill_dir: Path) -> None:
    """Sync a seed's bundle files (e.g. ``scripts/``) alongside its stored SKILL.md."""
    for path, relative in iter_bundle_files(skill_dir):
        storage_path = get_skill_file_path(SkillType.PREBUILT, skill_id, relative)
        if path.suffix in _TEXT_BUNDLE_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            if not await _stored_matches(storage, storage_path, text.encode("utf-8")):
                await storage.write_text(storage_path, text)
        else:
            data = path.read_bytes()
            if not await _stored_matches(storage, storage_path, data):
                await storage.write(storage_path, data)
