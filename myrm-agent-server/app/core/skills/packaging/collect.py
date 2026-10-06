"""Skill file collection for export (business layer).

[INPUT]
- myrm_agent_harness.agent.skills.market.helpers::ORIGIN_FILENAME (POS: install provenance file name.)
- myrm_agent_harness.agent.skills.market.transaction::RECEIPT_FILENAME (POS: install receipt file name.)
- ._helpers::_sync_skill_md_version (POS: frontmatter version sync with lineage.)

[OUTPUT]
- SkillFileSource: the two read operations collection needs (satisfied by SkillsService).
- collect_skill_files: the exportable file tree of one skill (path -> bytes).

[POS]
Single collection path shared by single-skill export and expert export. Install
bookkeeping (provenance, receipt, storage metadata, evals snapshot) is excluded
because it holds machine-local paths and is regenerated on install.
"""

from __future__ import annotations

from typing import Protocol

from myrm_agent_harness.agent.skills.market.helpers import ORIGIN_FILENAME
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.agent.skills.market.transaction import RECEIPT_FILENAME
from myrm_agent_harness.agent.skills.packaging import EVALS_FILE
from myrm_agent_harness.toolkits.storage.paths import SKILL_METADATA_FILE

from ._helpers import _sync_skill_md_version

__all__ = ["SkillFileSource", "collect_skill_files"]

_BOOKKEEPING_FILES = frozenset({SKILL_METADATA_FILE, EVALS_FILE, ORIGIN_FILENAME, RECEIPT_FILENAME})


class SkillFileSource(Protocol):
    """Read access to a stored skill's files."""

    async def list_skill_files(self, skill_id: str) -> list[str]: ...

    async def get_skill_file(self, skill_id: str, file_path: str) -> bytes | None: ...


async def collect_skill_files(
    source: SkillFileSource,
    skill_id: str,
    *,
    lineage_version: int | None = None,
) -> dict[str, bytes]:
    """Read the exportable file tree of ``skill_id`` (empty files are skipped).

    When ``lineage_version`` is known, the SKILL.md frontmatter version is
    synced to it so the package carries the real evolution version.
    """
    files: dict[str, bytes] = {}
    for path in sorted(await source.list_skill_files(skill_id)):
        if path in _BOOKKEEPING_FILES:
            continue
        content = await source.get_skill_file(skill_id, path)
        if not content:
            continue
        if path == SKILL_MD_FILE and lineage_version is not None:
            text = content.decode("utf-8", errors="replace")
            synced = _sync_skill_md_version(text, str(lineage_version))
            if synced != text:
                content = synced.encode("utf-8")
        files[path] = content
    return files
