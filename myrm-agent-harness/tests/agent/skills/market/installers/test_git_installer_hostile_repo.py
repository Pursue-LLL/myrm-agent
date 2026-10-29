"""Installing from a git repository whose author controls its links, paths and file sizes (real ``git``, local repos).

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.git_installer: `GitInstaller.download` (a real shallow clone)
- tests.support.git_probe: real ``git`` helpers

[OUTPUT]
- A symlink to a file or a directory outside the clone is not installed; a `subdirectory` that leaves the clone is
  refused; a file over the size limit is refused; a skill whose SKILL.md is a symlink to another file of the same
  repository installs

[POS]
Enforcement tests for the git install path: the repository is untrusted input, so each vector is a committed repository
cloned the way the market clones it.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.market.installers.git_installer import GitInstaller
from myrm_agent_harness.agent.skills.market.sanitizer import MAX_SINGLE_FILE_SIZE
from tests.support.git_probe import git, repository

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX symlinks and git"
)

SKILL_MD = b"---\nname: Alpha\ndescription: does alpha\n---\n# Alpha\n"


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))


@pytest.fixture
def secret(tmp_path: Path) -> Path:
    """A readable file and a skill directory that live next to, not inside, the repository."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside the clone")
    (outside / "SKILL.md").write_bytes(SKILL_MD)
    return outside


def _commit(repo: Path) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "payload")
    return f"file://{repo}"


def _repo(tmp_path: Path) -> Path:
    return repository(tmp_path / "repo", keep="README.md")


async def test_a_symlink_to_a_file_outside_the_clone_is_not_installed(tmp_path: Path, secret: Path) -> None:
    repo = _repo(tmp_path)
    skill = repo / "skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(SKILL_MD)
    os.symlink(secret / "secret.txt", skill / "absolute.txt")
    os.symlink("../" * 24 + "etc/hosts", skill / "relative.txt")

    result = await GitInstaller().download(_commit(repo), "skills/alpha")

    assert set(result.files) == {"SKILL.md"}


async def test_a_symlinked_directory_outside_the_clone_is_not_installed(tmp_path: Path, secret: Path) -> None:
    repo = _repo(tmp_path)
    os.symlink(secret, repo / "linked", target_is_directory=True)

    with pytest.raises(ValueError, match=r"SKILL\.md not found"):
        await GitInstaller().download(_commit(repo))


async def test_a_subdirectory_that_leaves_the_clone_is_refused(tmp_path: Path, secret: Path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(ValueError, match="outside base directory"):
        await GitInstaller().download(_commit(repo), "../outside")


async def test_a_subdirectory_that_is_a_symlink_outside_the_clone_is_refused(tmp_path: Path, secret: Path) -> None:
    repo = _repo(tmp_path)
    os.symlink(secret, repo / "linked", target_is_directory=True)

    with pytest.raises(ValueError, match="outside base directory"):
        await GitInstaller().download(_commit(repo), "linked")


async def test_a_skill_md_that_links_to_another_file_of_the_repository_installs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "agents").mkdir()
    (repo / "agents" / "alpha.md").write_bytes(SKILL_MD)
    mirror = repo / ".gemini" / "skills" / "alpha"
    mirror.mkdir(parents=True)
    os.symlink("../../../agents/alpha.md", mirror / "SKILL.md")

    result = await GitInstaller().download(_commit(repo), ".gemini/skills/alpha")

    assert result.name == "Alpha"
    assert result.files == {"SKILL.md": SKILL_MD}


async def test_a_file_over_the_size_limit_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    skill = repo / "skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(SKILL_MD)
    (skill / "big.bin").write_bytes(b"\0" * (MAX_SINGLE_FILE_SIZE + 1))

    with pytest.raises(ValueError, match="exceeds size limit"):
        await GitInstaller().download(_commit(repo), "skills/alpha")
