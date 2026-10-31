"""Local skill directory lookup by directory name and by the names a skill is known by.

[INPUT]
- myrm_agent_harness.api.skills::parse_skill_frontmatter (POS: the frontmatter parse the local scan lists a skill by)
- app.core.skills.utils::normalize_skill_name, slugify_draft_skill_name (POS: the name the agent runtime lists a skill under; the directory name an approved draft is written under)
- myrm_agent_harness.agent.skills.market.sanitizer::SKILL_MD_FILE (POS: entry file name of a skill package)

[OUTPUT]
- local_skill_dir_named: the directory of the skill kept under a directory name, spelled as the volume lists it
- local_skill_dir_known_as: the one directory whose skill is known by a name
- approval_writes_into: whether approving a draft under a name writes into a skill's directory on this volume

[POS]
Blocking file system lookups in the primary local skills directory, without the security scan a full local scan
runs per skill. SkillsService runs the second one off the event loop.
"""

from __future__ import annotations

import errno
import logging
import os
from pathlib import Path

from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.api.skills import parse_skill_frontmatter

from ..utils import normalize_skill_name, slugify_draft_skill_name

logger = logging.getLogger(__name__)


def local_skill_dir_named(skills_root: Path, dir_name: str) -> Path | None:
    """The directory below ``skills_root`` that holds a SKILL.md and is called ``dir_name``, ``None`` when there is none.

    Directory names are not held to the skill-name convention. An empty name, ``..`` and a name of more than one
    path component are refused: they would name no directory below ``skills_root``, or one outside it. A name longer
    than a directory entry can be is no skill either; any other file system error is raised, because the growth
    lifecycle takes a missing skill for one that is not locked. The directory is returned as the volume lists it:
    on a case-insensitive volume another spelling opens it too, but a skill's page id, and so its lock, belong to the
    listed one.
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
    return _as_listed(skills_root, skill_dir) if has_skill_md else None


def _as_listed(skills_root: Path, skill_dir: Path) -> Path:
    """``skill_dir`` under the name ``skills_root`` lists it by; ``skill_dir`` itself when it already is that name."""
    names = os.listdir(skills_root)
    if skill_dir.name in names:
        return skill_dir
    # The spelling differs from every entry, so only a volume that does not tell spellings apart opened it: the entry
    # it opened is the one that is the same file. Sorted, so that links to one directory give the same answer each time.
    for name in sorted(names):
        try:
            if (skills_root / name).samefile(skill_dir):
                return skills_root / name
        except OSError:
            continue
    return skill_dir


def approval_writes_into(skill_dir: Path, name: str) -> bool:
    """Whether approving a draft named ``name``, without a name override, writes into ``skill_dir``.

    Approval writes the draft under ``slugify_draft_skill_name(name)`` in the skills directory, so the answer is
    whether the volume resolves that one entry to ``skill_dir``: the directory's own name does, so does a link to it,
    and on a volume that does not tell spellings apart so does another spelling of its name. A name is judged by the
    name it is rewritten to: ``report builder`` writes into ``report-builder``, and a path is flattened into one name,
    so only a directory of that name is written into.
    """
    try:
        return os.path.samefile(skill_dir.parent / slugify_draft_skill_name(name), skill_dir)
    except OSError:
        return False


def _known_names(skill_dir: Path) -> frozenset[str]:
    """The names the skill in ``skill_dir`` goes by.

    They are the name the local scan lists it under (its name in SKILL.md; the directory's when it has none or the name
    is longer than a skill name may be) and the name the agent runtime lists it under. A directory entry the scan would
    not list (no SKILL.md, or one that fails to load for any reason) and one with a blank name go by none: as in the
    scan, one broken skill must not hide the others, and it could not be patched anyway.
    """
    skill_md = skill_dir / SKILL_MD_FILE
    try:
        if not skill_md.is_file():
            return frozenset()
        frontmatter = parse_skill_frontmatter(skill_md.read_text(encoding="utf-8"), skill_dir.name)
    except Exception as exc:
        logger.warning("Skipping unusable %s: %s", skill_md, exc)
        return frozenset()
    name = frontmatter.name or skill_dir.name
    if not name.strip():
        return frozenset()
    return frozenset({name, normalize_skill_name(name)})


def local_skill_dir_known_as(skills_root: Path, name: str) -> Path | None:
    """The directory below ``skills_root`` of the one skill known by ``name``, ``None`` when no skill or several are.

    A background review is shown the names the agent runtime lists skills under, which are neither the directory
    name nor, for most skills, the name in SKILL.md. Two skills that go by the same name cannot be told apart, so
    neither is chosen and the clash is logged. An unreadable ``skills_root`` is raised, for the reason
    ``local_skill_dir_named`` gives.
    """
    if not name.strip():
        return None
    try:
        entries = list(skills_root.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return None
    matches = [entry for entry in entries if name in _known_names(entry)]
    if len(matches) > 1:
        clashing = ", ".join(sorted(entry.name for entry in matches))
        logger.warning("Skill name %r is known by %d local skills (%s); none is chosen", name, len(matches), clashing)
    return matches[0] if len(matches) == 1 else None
