"""Local skill discovery for the curator: which skills exist, and which of them were installed.

[INPUT]
- myrm_agent_harness.backends.skills.local::LocalSkillBackend (POS: Local skill directory scanner)
- myrm_agent_harness.agent.skills.market.helpers::ORIGIN_FILENAME (POS: Market install provenance file name)
- myrm_agent_harness.backends.skills.types::SkillMetadata (POS: Skill metadata)
- app.core.skills.models::DEFAULT_LOCAL_SKILL_PATHS (POS: Skill roots; the first one is the primary root)

[OUTPUT]
- LocalSkillScan: Every scanned skill plus the names of those that were installed rather than authored here
- scan_local_skills: Scan all skill roots in one pass

[POS]
The single answer to "what does a sweep look at, and what did the user install?". The sweep, the
consolidation passes and the health probe all ask here, so they can never disagree about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.agent.skills.market.helpers import ORIGIN_FILENAME
from myrm_agent_harness.backends.skills.local import LocalSkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.skills import models

# The first root is the one Myrm writes to (see ``DEFAULT_LOCAL_SKILL_PATHS``); every other root
# belongs to another tool (Cursor, Claude Code, Codex, ...) that Myrm only reads.
_PRIMARY_ROOT_INDEX = 0


@dataclass(frozen=True, slots=True)
class LocalSkillScan:
    """Result of scanning every local skill root."""

    skills: list[SkillMetadata]
    installed_names: frozenset[str]
    """Skills a market install produced, or that live in another tool's root. Keyed by name, like the bound skills."""


async def scan_local_skills() -> LocalSkillScan:
    """Scan every existing skill root and mark which skills the user installed instead of authored.

    A skill counts as installed when it carries the market's ``origin.json`` or sits outside the
    primary root: the sweep sees only Myrm's own runs, so another tool's skill would otherwise look
    idle however much that tool uses it.
    """
    skills: list[SkillMetadata] = []
    installed: set[str] = set()
    for index, root in enumerate(models.DEFAULT_LOCAL_SKILL_PATHS):
        expanded = Path(root).expanduser()
        if not expanded.exists():
            continue
        found = await LocalSkillBackend(expanded, use_snapshot=False).list_skills()
        skills.extend(found)
        installed.update(skill.name for skill in found if index != _PRIMARY_ROOT_INDEX or _has_origin_record(skill))
    return LocalSkillScan(skills=skills, installed_names=frozenset(installed))


def _has_origin_record(skill: SkillMetadata) -> bool:
    return skill.storage_path is not None and (Path(skill.storage_path) / ORIGIN_FILENAME).is_file()
