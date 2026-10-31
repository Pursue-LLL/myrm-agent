"""Local skill directory lookup by directory name and by the names a skill is known by.

[INPUT]
- app.core.skills.providers.local::parse_skill_md (POS: SKILL.md frontmatter reader of the local provider)
- app.core.skills.utils::normalize_skill_name (POS: the name the agent runtime lists a skill under)
- myrm_agent_harness.agent.skills.market.sanitizer::SKILL_MD_FILE (POS: entry file name of a skill package)

[OUTPUT]
- local_skill_dir_named: the directory of the skill kept under a directory name
- local_skill_dir_listed_as: the one directory whose skill is known by a name

[POS]
Blocking file system lookups in the primary local skills directory, without the security scan a full local scan
runs per skill. SkillsService runs the second one off the event loop.
"""

from __future__ import annotations

import errno
import logging
from pathlib import Path

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

from ..providers.local import parse_skill_md
from ..utils import normalize_skill_name

logger = logging.getLogger(__name__)


def local_skill_dir_named(skills_root: Path, dir_name: str) -> Path | None:
    """The directory below ``skills_root`` that holds a SKILL.md and is called ``dir_name``, ``None`` when there is none.

    Directory names are not held to the skill-name convention. An empty name, ``..`` and a name of more than one
    path component are refused: they would name no directory below ``skills_root``, or one outside it. A name longer
    than a directory entry can be is no skill either; any other file system error is raised, because the growth
    lifecycle takes a missing skill for one that is not locked.
    """
    if not dir_name or dir_name == ".." or Path(dir_name).name != dir_name:
        return None
    skill_dir = skills_root / dir_name
    try:
        has_skill_md = (skill_dir / SKILL_MD_FILE).is_file()
    except OSError as exc:
        if exc.errno != errno.ENAMETOOLONG:
            raise
        return None
    return skill_dir if has_skill_md else None


def _known_names(skill_dir: Path) -> frozenset[str]:
    """The names the skill in ``skill_dir`` goes by.

    They are its name in SKILL.md (the directory's when it has none) and the name the agent runtime lists it under. A
    directory entry that holds no readable SKILL.md goes by none: one broken skill must not hide the others, and it
    could not be patched anyway.
    """
    skill_md = skill_dir / SKILL_MD_FILE
    try:
        if not skill_md.is_file():
            return frozenset()
        frontmatter = parse_skill_md(skill_md.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Skipping unreadable %s: %s", skill_md, exc)
        return frozenset()
    name = str((frontmatter or {}).get("name") or "").strip() or skill_dir.name
    return frozenset({name, normalize_skill_name(name)})


def local_skill_dir_listed_as(skills_root: Path, name: str) -> Path | None:
    """The directory below ``skills_root`` of the one skill known by ``name``, ``None`` when no skill or several are.

    A background review is shown the names the agent runtime lists skills under, which are neither the directory
    name nor, for most skills, the name in SKILL.md. Two skills that go by the same name cannot be told apart, so
    neither is chosen. An unreadable ``skills_root`` is raised, for the reason ``local_skill_dir_named`` gives.
    """
    if not name.strip():
        return None
    try:
        entries = list(skills_root.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return None
    matches = [entry for entry in entries if name in _known_names(entry)]
    return matches[0] if len(matches) == 1 else None
