"""Collect pre-replace skill tree snapshots for rollback batches.

[INPUT]
- app.core.skills.store.service::skills_service (POS: file listing and reads)

[OUTPUT]
- collect_manifest_snapshot_contents: SKILL.md + text resource map for batch metadata

[POS]
Skill Change Contract snapshot collector. Keeps snapshots bounded for SQLite batch rows.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

from app.core.storage.paths import SKILL_METADATA_FILE

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_FILES = 80
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
_TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".txt",
        ".py",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".sh",
        ".bash",
        ".zsh",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".css",
        ".html",
        ".xml",
        ".csv",
        ".ini",
        ".cfg",
        ".env.example",
    }
)


def _is_snapshot_candidate(relative_path: str) -> bool:
    name = PurePosixPath(relative_path).name
    if name.startswith("."):
        return False
    if relative_path in {SKILL_METADATA_FILE, "origin.json", ".stats.json", ".replace_state.json"}:
        return False
    suffix = PurePosixPath(relative_path).suffix.lower()
    if relative_path == SKILL_MD_FILE:
        return True
    return suffix in _TEXT_SUFFIXES


async def collect_manifest_snapshot_contents(skill_id: str) -> tuple[str, dict[str, str], bool]:
    """Return (skill_md_content, resource_files excluding SKILL.md, snapshot_truncated)."""
    from app.core.skills.store.service import skills_service

    skill_md_raw = await skills_service.get_skill_file(skill_id, SKILL_MD_FILE)
    if skill_md_raw is None:
        raise FileNotFoundError(f"Missing {SKILL_MD_FILE} for skill {skill_id}")
    skill_md = skill_md_raw.decode("utf-8") if isinstance(skill_md_raw, bytes) else skill_md_raw

    files = await skills_service.list_skill_files(skill_id)
    resource_files: dict[str, str] = {}
    total_bytes = len(skill_md.encode("utf-8"))
    file_count = 0
    snapshot_truncated = False

    candidates = sorted(rel for rel in files if _is_snapshot_candidate(rel) and rel != SKILL_MD_FILE)
    for rel in candidates:
        if file_count >= MAX_SNAPSHOT_FILES:
            snapshot_truncated = True
            logger.warning(
                "Manifest snapshot truncated for %s: max files %s",
                skill_id,
                MAX_SNAPSHOT_FILES,
            )
            break
        raw = await skills_service.get_skill_file(skill_id, rel)
        if raw is None:
            continue
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        encoded_len = len(text.encode("utf-8"))
        if total_bytes + encoded_len > MAX_SNAPSHOT_BYTES:
            snapshot_truncated = True
            logger.warning(
                "Manifest snapshot truncated for %s: max bytes %s",
                skill_id,
                MAX_SNAPSHOT_BYTES,
            )
            break
        resource_files[rel] = text
        total_bytes += encoded_len
        file_count += 1

    return skill_md, resource_files, snapshot_truncated
