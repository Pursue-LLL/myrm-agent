"""Git skill install: the skill directory is decided inside the cloned repository.

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.git_installer: `GitInstaller`, `_walk_skill_dir`

[OUTPUT]
- Fails when a `subdirectory` that leaves the clone (`..`, an absolute path, a symlinked directory pointing outside)
  resolves to a directory whose files would be installed
- Fails when an ancestor of the skill directory decides which files count as hidden

[POS]
myrm-agent-harness/tests/agent/skills/market/installers/test_git_installer_containment.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.market.installers.git_installer import GitInstaller, _walk_skill_dir

SKILL_MD = b"---\nname: Alpha\ndescription: does alpha\n---\n# Alpha\n"


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    (root / "skills" / "alpha").mkdir(parents=True)
    (root / "skills" / "alpha" / "SKILL.md").write_bytes(SKILL_MD)
    return root


def _outside_skill(base: Path) -> Path:
    outside = base / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_bytes(SKILL_MD)
    (outside / "secret.txt").write_text("outside the clone")
    return outside


def test_parent_traversal_is_refused(clone: Path) -> None:
    _outside_skill(clone.parent)

    with pytest.raises(ValueError, match="escapes"):
        GitInstaller._resolve_skill_dir(clone, "../outside")


def test_absolute_path_outside_the_clone_is_refused(clone: Path) -> None:
    outside = _outside_skill(clone.parent)

    with pytest.raises(ValueError, match="escapes"):
        GitInstaller._resolve_skill_dir(clone, str(outside))


def test_symlinked_directory_pointing_outside_the_clone_is_refused(clone: Path) -> None:
    outside = _outside_skill(clone.parent)
    try:
        (clone / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ValueError, match="escapes"):
        GitInstaller._resolve_skill_dir(clone, "linked")


def test_subdirectory_that_returns_inside_the_clone_resolves(clone: Path) -> None:
    resolved = GitInstaller._resolve_skill_dir(clone, "skills/../skills/alpha")

    assert resolved.resolve() == (clone / "skills" / "alpha").resolve()


def test_collects_files_when_an_ancestor_of_the_skill_dir_is_hidden(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".cache" / "skill_git_x"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_bytes(SKILL_MD)
    (skill_dir / "run.py").write_text("print('x')")

    names = {p.name for p in _walk_skill_dir(skill_dir)}

    assert names == {"SKILL.md", "run.py"}
