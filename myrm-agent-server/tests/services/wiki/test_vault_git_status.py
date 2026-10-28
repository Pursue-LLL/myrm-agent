"""``/wiki/stats`` reports a vault's git history only when the repository is the vault's own.

[INPUT]
- app.services.wiki.vault.git_status::read_vault_git_status (POS: vault git visibility fields)
- git (POS: the real binary, never mocked)

[OUTPUT]
- Fails when a vault whose ``.git`` names another repository shows that repository's last commit as its own history,
  or when an own repository or a linked-worktree vault stops showing its history.

[POS]
The snapshot flow refuses a vault whose repository is not its own, so the status must not claim history is kept there.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.vault.git_status import read_vault_git_status

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")

_ENABLED = WikiConfig(enable_version_control=True)


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.email=a@example.com", "-c", "user.name=a", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _repository_with_a_commit(path: Path, subject: str) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    (path / "page.md").write_text("one\n")
    _git(path, "add", "page.md")
    _git(path, "commit", "-q", "-m", subject)
    return path


def _vault(path: Path) -> WikiStructure:
    structure = WikiStructure(path)
    structure.ensure_structure()
    return structure


def test_a_vault_with_version_control_off_reports_it_disabled(tmp_path: Path) -> None:
    status = read_vault_git_status(_vault(tmp_path / "vault"), WikiConfig(enable_version_control=False))

    assert (status.enabled, status.initialized, status.last_commit) == (False, False, None)


def test_a_vault_without_a_repository_is_not_initialized(tmp_path: Path) -> None:
    status = read_vault_git_status(_vault(tmp_path / "vault"), _ENABLED)

    assert (status.enabled, status.initialized, status.last_commit) == (True, False, None)


def test_a_vault_with_its_own_repository_shows_its_last_commit(tmp_path: Path) -> None:
    structure = _vault(tmp_path / "vault")
    _git(structure.base_dir, "init", "-q")
    _git(structure.base_dir, "add", "-A")
    _git(structure.base_dir, "commit", "-q", "--allow-empty", "-m", "myrm: first")

    status = read_vault_git_status(structure, _ENABLED)

    assert status.initialized is True
    assert status.last_commit is not None
    assert status.last_commit.endswith("myrm: first")


def test_a_vault_that_is_a_linked_worktree_shows_its_own_branch(tmp_path: Path) -> None:
    other = _repository_with_a_commit(tmp_path / "other", "someone else's work")
    structure = WikiStructure(tmp_path / "vault")
    _git(other, "worktree", "add", "-q", "-b", "vault-branch", str(structure.base_dir))
    structure.ensure_structure()
    _git(structure.base_dir, "commit", "-q", "--allow-empty", "-m", "myrm: vault")

    status = read_vault_git_status(structure, _ENABLED)

    assert status.initialized is True
    assert status.last_commit is not None
    assert status.last_commit.endswith("myrm: vault")


def test_a_vault_whose_git_file_names_another_repository_does_not_show_its_history(tmp_path: Path) -> None:
    other = _repository_with_a_commit(tmp_path / "other", "someone else's work")
    structure = _vault(tmp_path / "vault")
    (structure.base_dir / ".git").write_text(f"gitdir: {other / '.git'}\n")
    assert _git(structure.base_dir, "log", "-1", "--format=%s") == "someone else's work"

    status = read_vault_git_status(structure, _ENABLED)

    assert (status.enabled, status.initialized, status.last_commit) == (True, False, None)
