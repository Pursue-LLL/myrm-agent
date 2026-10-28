import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.goals.continuation_git_drift import (
    GitDriftStatus,
    _run_git_cmd,
    check_git_drift_and_rebase,
    inspect_git_drift,
)
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from tests.core.security._git_probe import clear, fired, git, plain, program, run


@pytest.fixture
def mock_goal():
    return Goal(
        goal_id="g-100",
        session_id="s-100",
        objective="Implement feature",
        status=GoalStatus.ACTIVE,
    )


@pytest.mark.asyncio
async def test_inspect_git_drift_non_git():
    with patch("myrm_agent_harness.agent.goals.continuation_git_drift._run_git_cmd") as mock_git:
        mock_git.return_value = (1, "fatal: not a git repository", "")
        status = await inspect_git_drift("/some/path")
        assert status.is_git_repo is False
        assert status.upstream is None
        assert status.behind_count == 0


@pytest.mark.asyncio
async def test_inspect_git_drift_with_upstream():
    with patch("myrm_agent_harness.agent.goals.continuation_git_drift._run_git_cmd") as mock_git:
        # 1: inside work tree -> (0, "true", "")
        # 2: upstream branch -> (0, "origin/main", "")
        # 3: behind count -> (0, "3", "")
        # 4: ahead count -> (0, "1", "")
        mock_git.side_effect = [
            (0, "true", ""),
            (0, "origin/main", ""),
            (0, "3", ""),
            (0, "1", ""),
        ]
        status = await inspect_git_drift("/workspace")
        assert status.is_git_repo is True
        assert status.upstream == "origin/main"
        assert status.behind_count == 3
        assert status.ahead_count == 1


@pytest.mark.asyncio
async def test_check_git_drift_rebase_success(mock_goal):
    provider = AsyncMock()
    with (
        patch(
            "myrm_agent_harness.agent.middlewares._session_context.get_workspace_root",
            return_value="/workspace",
        ),
        patch(
            "myrm_agent_harness.agent.goals.continuation_git_drift.inspect_git_drift",
            return_value=GitDriftStatus(is_git_repo=True, upstream="origin/main", behind_count=2),
        ),
        patch(
            "myrm_agent_harness.agent.goals.continuation_git_drift._run_git_cmd",
            return_value=(0, "Successfully rebased", ""),
        ),
    ):
        decision = await check_git_drift_and_rebase(provider, mock_goal)
        assert decision is None
        provider.update_metadata.assert_called_once()
        meta = provider.update_metadata.call_args[0][1]
        assert meta["_last_git_drift_check"]["status"] == "success"
        assert meta["_last_git_drift_check"]["rebased_commits"] == 2


@pytest.mark.asyncio
async def test_check_git_drift_rebase_conflict_aborts_and_pauses(mock_goal):
    provider = AsyncMock()
    with (
        patch(
            "myrm_agent_harness.agent.middlewares._session_context.get_workspace_root",
            return_value="/workspace",
        ),
        patch(
            "myrm_agent_harness.agent.goals.continuation_git_drift.inspect_git_drift",
            return_value=GitDriftStatus(is_git_repo=True, upstream="origin/main", behind_count=4),
        ),
        patch(
            "myrm_agent_harness.agent.goals.continuation_git_drift._run_git_cmd",
        ) as mock_git,
    ):
        # First call is git rebase --autostash origin/main -> fails with conflict
        # Second call is git rebase --abort -> succeeds
        mock_git.side_effect = [
            (1, "CONFLICT (content): Merge conflict in file.py", "error: could not apply"),
            (0, "", ""),
        ]
        decision = await check_git_drift_and_rebase(provider, mock_goal)
        assert decision is not None
        assert decision.should_continue is False
        assert decision.verdict == "drift_pause"
        assert "DRIFT_CONFLICT_HUMAN_ESCALATION" in decision.reason

        provider.update_status.assert_called_once_with(mock_goal.goal_id, GoalStatus.PAUSED)
        provider.update_metadata.assert_called_once()
        meta = provider.update_metadata.call_args[0][1]
        assert meta["_last_git_drift_check"]["status"] == "conflict_aborted"


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("git") is None, reason="needs POSIX shell scripts and git")
@pytest.mark.asyncio
async def test_the_unattended_rebase_runs_no_hook_or_fsmonitor_the_repository_chose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    markers = tmp_path / "markers"
    markers.mkdir()

    def behind_clone(name: str) -> Path:
        upstream = tmp_path / f"{name}-upstream"
        upstream.mkdir()
        git(upstream, "init", "-q")
        git(upstream, "config", "user.email", "a@example.com")
        git(upstream, "config", "user.name", "a")
        (upstream / "f.txt").write_text("one\n")
        git(upstream, "add", "f.txt")
        git(upstream, "commit", "-q", "-m", "first")
        clone = tmp_path / name
        run(["git", "clone", "-q", str(upstream), str(clone)], tmp_path)
        git(clone, "config", "user.email", "a@example.com")
        git(clone, "config", "user.name", "a")
        (upstream / "g.txt").write_text("g\n")
        git(upstream, "add", "g.txt")
        git(upstream, "commit", "-q", "-m", "upstream moves on")
        git(clone, "fetch", "-q")
        git(clone, "status", "--porcelain")  # an index must exist before git consults the monitor
        (clone / "f.txt").write_text("dirty\n")
        hook = clone / ".git" / "hooks" / "pre-rebase"
        hook.write_text(f"#!/bin/sh\ntouch '{markers}/hook'\n")
        hook.chmod(0o755)
        git(clone, "config", "core.fsmonitor", program(markers, "fsmonitor"))
        return clone

    control = behind_clone("control")
    run(plain(control, "rebase", "--autostash", "@{u}"), control)
    if "hook" not in fired(markers):
        pytest.skip("this git build does not run the pre-rebase hook here")
    clear(markers)

    victim = behind_clone("victim")
    code, _, stderr = await _run_git_cmd(["rebase", "--autostash", "@{u}"], str(victim))

    assert code == 0, stderr
    assert fired(markers) == set()
    assert (victim / "f.txt").read_text() == "dirty\n"
