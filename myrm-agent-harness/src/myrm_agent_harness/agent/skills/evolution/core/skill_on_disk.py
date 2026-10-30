"""The SKILL.md of a skill as it is on disk, the text the evolution engine works from.

The evolution store keeps a copy of every skill's text, but the file is what the agent loads, and what the editor,
a version rollback and the agent's skill tool change without touching the copy. A proposal built from the copy
would diff against, and on approval overwrite, text the skill no longer has.

[INPUT]
- agent.skills.evolution.core.types::SkillRecord (POS: Complete skill record with evolution metadata.)
- agent.skills.evolution.db.store::SkillStore (POS: SQLite persistence for skill evolution system; its content size limit)
- backends.skills._runtime::compute_content_hash, read_skill_md (POS: line-ending-insensitive content hash; the SKILL.md text at a path)

[OUTPUT]
- skill_from_disk: The skill with its content replaced by the SKILL.md on disk when that text differs.

[POS]
Disk source of the evolution engine. Read-only: the store's copy is left as it is, a later apply writes it.
"""

import logging
from dataclasses import replace
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.backends.skills._runtime import compute_content_hash, read_skill_md

logger = logging.getLogger(__name__)

__all__ = ["skill_from_disk"]


def skill_from_disk(skill: SkillRecord) -> SkillRecord:
    """The skill as its SKILL.md holds it; ``skill`` itself when the file is missing, unreadable, the same text or too large.

    A file larger than the store takes is not evolved from: the model input stays within the size the store holds.
    """
    text = read_skill_md(Path(skill.path)) if skill.path else None
    if text is None or compute_content_hash(text) == compute_content_hash(skill.content):
        return skill
    if len(text) > SkillStore.MAX_SKILL_CONTENT_CHARS:
        logger.warning("SKILL.md of '%s' is larger than the evolution store takes; its stored copy is used", skill.name)
        return skill
    logger.info("SKILL.md of '%s' differs from the evolution store's copy; evolving the file's text", skill.name)
    return replace(skill, content=text)
