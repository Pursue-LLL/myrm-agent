"""Git skill install: the skill directory is decided inside the cloned repository.

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.git_installer: `GitInstaller`

[OUTPUT]
- Fails when a `subdirectory` that leaves the clone (`..`, an absolute path, a symlinked directory pointing outside)
  would resolve to a directory whose files get installed
- Resolves a `subdirectory` that leaves and re-enters the clone

[POS]
myrm-agent-harness/tests/agent/skills/market/installers/test_git_installer_containment.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.market.installers.git_installer import GitInstaller

SKILL_MD = b"---\nname: Alpha\ndescription: does alpha\n---\n# Alpha\n"
REFUSED = r"outside base directory|Absolute paths are not allowed"


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

    with pytest.raises(ValueError, match=REFUSED):
        GitInstaller._resolve_skill_dir(clone, "../outside")


def test_absolute_path_outside_the_clone_is_refused(clone: Path) -> None:
    outside = _outside_skill(clone.parent)

    with pytest.raises(ValueError, match=REFUSED):
        GitInstaller._resolve_skill_dir(clone, str(outside))


def test_symlinked_directory_pointing_outside_the_clone_is_refused(clone: Path) -> None:
    outside = _outside_skill(clone.parent)
    try:
        (clone / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ValueError, match=REFUSED):
        GitInstaller._resolve_skill_dir(clone, "linked")


def test_subdirectory_that_returns_inside_the_clone_resolves(clone: Path) -> None:
    resolved = GitInstaller._resolve_skill_dir(clone, "skills/../skills/alpha")

    assert resolved.resolve() == (clone / "skills" / "alpha").resolve()
