"""The SKILL.md of a skill as it is on disk, the text and the evolution lock the evolution engine works from.

The evolution store keeps a copy of every skill's text and an evolution-lock flag, but the file is what the agent
loads, and what the editor, a version rollback and the agent's skill tool change without touching the copy. A
proposal built from the copy would diff against, and on approval overwrite, text the skill no longer has; a lock
written into the file only (a freshly created skill carries it there) would go unseen.

[INPUT]
- agent.skills.evolution.core.types::SkillRecord (POS: Complete skill record with evolution metadata.)
- agent.skills.evolution.db.store::SkillStore (POS: SQLite persistence for skill evolution system; its content size limit)
- backends.skills._runtime::compute_content_hash, read_skill_md (POS: line-ending-insensitive content hash; the SKILL.md text at a path)
- backends.skills._utils::parse_skill_frontmatter, SkillMetadataError (POS: the SKILL.md frontmatter parser, its evolution-lock flag)

[OUTPUT]
- skill_from_disk: The skill with the SKILL.md text on disk when it differs, and locked when the store or the file says so.

[POS]
Disk source of the evolution engine and screener. Read-only: the store's copy is left as it is, a later apply writes it.
"""

import logging
from dataclasses import replace
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.backends.skills._runtime import compute_content_hash, read_skill_md
from myrm_agent_harness.backends.skills._utils import SkillMetadataError, parse_skill_frontmatter

logger = logging.getLogger(__name__)

__all__ = ["skill_from_disk"]


def skill_from_disk(skill: SkillRecord) -> SkillRecord:
    """The skill as its SKILL.md holds it; ``skill`` itself when neither its text nor its lock differs.

    The text is the file's unless the file is missing, unreadable, the same text or larger than the store takes (the
    model input stays within the size the store holds). The skill is locked when the store's flag or the file's
    frontmatter says so; a file without a frontmatter the loaders accept does not lock, and an unreadable one falls
    back to the frontmatter of the stored copy.
    """
    text = read_skill_md(Path(skill.path)) if skill.path else None
    content = skill.content
    if text is not None and compute_content_hash(text) != compute_content_hash(content):
        if len(text) > SkillStore.MAX_SKILL_CONTENT_CHARS:
            logger.warning(
                "SKILL.md of '%s' is larger than the evolution store takes; its stored copy is used", skill.name
            )
        else:
            logger.info("SKILL.md of '%s' differs from the evolution store's copy; using the file's text", skill.name)
            content = text
    locked = skill.evolution_locked or _frontmatter_locks_evolution(skill.name, content if text is None else text)
    if content is skill.content and locked == skill.evolution_locked:
        return skill
    return replace(skill, content=content, evolution_locked=locked)


def _frontmatter_locks_evolution(name: str, text: str) -> bool:
    try:
        return parse_skill_frontmatter(text, name).evolution_locked
    except SkillMetadataError:
        return False
