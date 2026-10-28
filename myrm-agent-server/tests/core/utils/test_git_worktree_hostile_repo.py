"""The server's worktree git helpers run no program or transport a repository's own config names.

[INPUT]
- app.core.utils.git_worktree (POS: shared worktree / commit / merge git helpers)
- app.services.kanban.race_lane_diff (POS: lane diff review reads)

[OUTPUT]
- Real ``git`` runs in repositories whose config or hooks name marker-writing programs: fsmonitor, a merge driver, a
  partial clone's upload-pack and a ``reference-transaction`` hook each fire on the plain command and stay silent
  through the helpers.

[POS]
Wiring tests for ``_run_git``: the architecture guard proves no bare spawn exists, these prove the hardened argv is the
one that is actually used by the flows the kanban board and chat sandbox run outside the agent sandbox.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from myrm_agent_harness.api.security import GitHardeningError

from app.core.utils import git_worktree
from app.core.utils.git_worktree import (
    WorktreeCreateError,
    WorktreeErrorReason,
    _delete_git_branch,
    _git_worktree_add,
    _merge_branch_into_current,
    _run_git,
    _worktree_is_dirty,
)
from app.services.git.worktree_service import GitWorktreeService, WorktreeCreateFailed

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git"
)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)


def _program(markers: Path, name: str, body: str = "") -> str:
    script = markers.parent / f"{name}.sh"
    script.write_text(f"#!/bin/sh\ntouch '{markers}/{name}'\n{body}\n")
    script.chmod(0o755)
    return str(script)


def _fired(markers: Path) -> set[str]:
    return {entry.name for entry in markers.iterdir()}


def _clear(markers: Path) -> None:
    for entry in markers.iterdir():
        entry.unlink()


@pytest.fixture(autouse=True)
def _isolated_git_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No user or system git config, and no inherited transport allow-list, in the helper's own environment."""
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("")
    environment = {key: value for key, value in git_worktree._GIT_ENV.items() if key != "GIT_ALLOW_PROTOCOL"}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(global_config)})
    monkeypatch.setattr(git_worktree, "_GIT_ENV", environment)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GIT_ALLOW_PROTOCOL", raising=False)


@pytest.fixture
def markers(tmp_path: Path) -> Path:
    directory = tmp_path / "markers"
    directory.mkdir()
    return directory


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _git(workspace, "init", "-q", "-b", "main")
    _git(workspace, "config", "user.email", "a@example.com")
    _git(workspace, "config", "user.name", "a")
    (workspace / "f.txt").write_text("one\n")
    _git(workspace, "add", "f.txt")
    _git(workspace, "commit", "-q", "-m", "init")
    return workspace


@pytest.mark.asyncio
async def test_a_status_check_does_not_run_the_repositorys_fsmonitor(repo: Path, markers: Path) -> None:
    (repo / "f.txt").write_text("two\n")
    _git(repo, "status", "--porcelain")  # an index must exist before git consults the monitor
    _git(repo, "config", "core.fsmonitor", _program(markers, "fsmonitor"))
    _git(repo, "status", "--porcelain")
    if "fsmonitor" not in _fired(markers):
        pytest.skip("this git build does not run fsmonitor for `git status`")
    _clear(markers)

    assert await _worktree_is_dirty(str(repo)) is True
    assert _fired(markers) == set()


@pytest.mark.asyncio
async def test_a_merge_driver_the_repository_names_does_not_run(repo: Path, markers: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "f.txt").write_text("one\ntopic\n")
    _git(repo, "commit", "-q", "-am", "topic edits f.txt")
    _git(repo, "checkout", "-q", "main")
    (repo / ".gitattributes").write_text("f.txt merge=evil\n")
    (repo / "f.txt").write_text("one\nmain\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "main edits f.txt and names a driver")
    _git(repo, "config", "merge.evil.driver", _program(markers, "driver", "exit 0"))
    _git(repo, "merge", "-q", "--no-ff", "-m", "m", "topic")
    if "driver" not in _fired(markers):
        pytest.skip("this git build does not run the merge driver here")
    _git(repo, "reset", "-q", "--hard", "ORIG_HEAD")
    _clear(markers)

    merged, _conflicts, _stderr = await _merge_branch_into_current(str(repo), "topic", "m")

    assert merged is False
    assert _fired(markers) == set()
    assert _git(repo, "status", "--porcelain").stdout == "", "a refused merge must leave the repository usable"


@pytest.mark.asyncio
@pytest.mark.parametrize("merged_only", [False, True])
async def test_deleting_a_branch_does_not_run_the_repositorys_reference_transaction_hook(
    repo: Path, markers: Path, merged_only: bool
) -> None:
    """Every ref the application deletes after a lane or chat sandbox ends fires this hook on the plain command."""
    _git(repo, "branch", "control")
    _git(repo, "branch", "lane")
    hook = repo / ".git" / "hooks" / "reference-transaction"
    shutil.copy(_program(markers, "reference-transaction"), hook)
    _git(repo, "branch", "-D", "control")
    if "reference-transaction" not in _fired(markers):
        pytest.skip("this git build does not run the reference-transaction hook for `git branch -D`")
    _clear(markers)

    assert await _delete_git_branch(str(repo), "lane", merged_only=merged_only) is True

    assert _fired(markers) == set()
    assert _git(repo, "branch", "--list", "lane").stdout.strip() == "", "the branch must still be deleted"


@pytest.mark.asyncio
async def test_creating_a_worktree_in_a_partial_clone_does_not_fetch_through_the_repositorys_program(
    tmp_path: Path, markers: Path
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q", "-b", "main")
    _git(source, "config", "user.email", "a@example.com")
    _git(source, "config", "user.name", "a")
    _git(source, "config", "uploadpack.allowFilter", "true")
    _git(source, "config", "uploadpack.allowAnySHA1InWant", "true")
    for text in ("one\n", "one\ntwo\n"):
        (source / "f.txt").write_text(text)
        _git(source, "add", "f.txt")
        _git(source, "commit", "-q", "-m", text.strip())

    def clone(name: str) -> Path:
        destination = tmp_path / name
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "clone",
                "-q",
                "--filter=blob:none",
                "--no-checkout",
                f"file://{source}",
                str(destination),
            ],
            check=True,
            capture_output=True,
        )
        _git(destination, "config", "remote.origin.uploadpack", _program(markers, "uploadpack", 'exec git-upload-pack "$@"'))
        return destination

    control = clone("control")
    _git(control, "worktree", "add", "--detach", str(tmp_path / "control-wt"), "HEAD")
    if "uploadpack" not in _fired(markers):
        pytest.skip("this git build does not fetch while checking out a worktree")
    _clear(markers)

    victim = clone("victim")
    _clear(markers)
    outcome = await _git_worktree_add(str(victim), "lane", str(tmp_path / "victim-wt"), "victim-wt", context="test")

    assert _fired(markers) == set()
    assert isinstance(outcome, WorktreeCreateError), "the missing file content must be an error, not a fetch"


@pytest.mark.asyncio
async def test_a_repository_that_cannot_be_neutralised_is_reported_to_the_worktree_service_as_a_value_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(*_args: object, **_kwargs: object) -> None:
        raise GitHardeningError("Repository git configuration key cannot be neutralised: 'filter.a=b.clean'")

    monkeypatch.setattr("app.services.git.worktree_service._run_git", refuse)

    with pytest.raises(ValueError, match="git cannot be run safely") as refused:
        await GitWorktreeService().create_worktree("lane", repo_path=str(repo))

    assert isinstance(refused.value, WorktreeCreateFailed)
    assert refused.value.reason is WorktreeErrorReason.UNSAFE_REPOSITORY


@pytest.mark.asyncio
async def test_a_refused_lane_read_is_a_failed_command_not_an_exception(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuse(*_args: object, **_kwargs: object) -> None:
        raise GitHardeningError("refused")

    importlib.import_module("app.services.kanban.race_orchestrator")  # the pair only imports in this order
    lane_diff = importlib.import_module("app.services.kanban.race_lane_diff")
    monkeypatch.setattr(lane_diff, "_run_git", refuse)

    result = await lane_diff._run_lane_git(str(repo), ("diff", "--numstat", "a...b", "--"))

    assert result.returncode == 1
    assert "refused" in result.stderr


@pytest.mark.asyncio
async def test_the_helper_passes_the_callers_config_after_the_hardened_overrides(repo: Path) -> None:
    result = await _run_git(("config", "--get", "user.name"), cwd=str(repo), timeout=5, config=("user.name=Override",))

    assert result.stdout.strip() == "Override"


@pytest.mark.asyncio
async def test_the_helper_runs_git_without_a_credential_prompt(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Checking out a worktree can make git-lfs ask for credentials; the server has no one to answer."""
    environments: list[dict[str, str]] = []
    real_run = subprocess.run

    def spy(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[-1] == "HEAD" and isinstance(kwargs.get("env"), dict):
            environments.append(dict(kwargs["env"]))  # type: ignore[arg-type]
        return real_run(argv, **kwargs)  # type: ignore[call-overload,no-any-return]

    monkeypatch.setattr(subprocess, "run", spy)

    await _run_git(("rev-parse", "HEAD"), cwd=str(repo), timeout=5)

    assert [env.get("GIT_TERMINAL_PROMPT") for env in environments] == ["0"]


def _plant_conditional_include(repo: Path) -> None:
    """A repository-local conditional include is the one config shape the helper cannot neutralise key by key."""
    _git(repo, "config", "includeIf.onbranch:main.path", "/nonexistent/included.config")


@pytest.mark.asyncio
async def test_a_refused_repository_is_reported_as_unsafe_not_as_a_generic_failure(repo: Path, tmp_path: Path) -> None:
    _plant_conditional_include(repo)
    target = tmp_path / "wt"

    outcome = await _git_worktree_add(str(repo), "lane", str(target), "wt", context="test")

    assert isinstance(outcome, WorktreeCreateError)
    assert outcome.reason is WorktreeErrorReason.UNSAFE_REPOSITORY
    assert not target.exists()


@pytest.mark.asyncio
async def test_the_worktree_service_refuses_a_repository_with_a_conditional_include(repo: Path) -> None:
    _plant_conditional_include(repo)

    with pytest.raises(WorktreeCreateFailed) as refused:
        await GitWorktreeService().create_worktree("lane", repo_path=str(repo))

    assert refused.value.reason is WorktreeErrorReason.UNSAFE_REPOSITORY
    assert not (repo / ".worktrees" / "lane").exists()
