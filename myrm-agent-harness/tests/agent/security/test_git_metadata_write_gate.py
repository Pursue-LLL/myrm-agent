"""A write into executable git metadata asks the human on every channel.

``.git/hooks`` scripts run on the user's next ``git commit`` and ``.git/config`` can name programs git runs
(``core.fsmonitor``, ``core.hooksPath``): a prompt-injected write there is code execution outside the
agent's supervision, so the permission engine puts the write to the human whatever the channel preset allows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.path_security import is_executable_git_metadata_file
from myrm_agent_harness.agent.security.types import PathPolicy, PermissionAction


@pytest.mark.parametrize(
    "path",
    [
        "/p/.git/hooks",
        "/p/.git/hooks/pre-commit",
        "/p/.git/config",
        "/p/.GIT/Hooks/pre-push",
        "/p/.git/modules/sub/hooks/post-merge",
        "/p/.git/modules/a/b/config",
        "C:\\p\\.git\\hooks\\pre-commit",
    ],
)
def test_executable_git_metadata_is_recognised(path: str) -> None:
    assert is_executable_git_metadata_file(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/p/.git/HEAD",
        "/p/.git/objects/ab/cdef",
        "/p/.git/hooks.md",
        "/p/hooks/pre-commit",
        "/p/src/config",
        "/p/.github/hooks/x",
        "/p/.gitignore",
        "",
    ],
)
def test_other_paths_are_not_executable_git_metadata(path: str) -> None:
    assert is_executable_git_metadata_file(path) is False


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    return tmp_path


def test_a_write_into_hooks_asks_even_inside_the_writable_workspace(workspace: Path) -> None:
    action, reason = check_path_policy(
        str(workspace / ".git" / "hooks" / "pre-commit"), PathPolicy(), str(workspace), require_write=True
    )

    assert action == PermissionAction.ASK
    assert "git" in reason.lower()


def test_reading_a_hook_needs_no_approval(workspace: Path) -> None:
    action, _ = check_path_policy(
        str(workspace / ".git" / "hooks" / "pre-commit.sample"), PathPolicy(), str(workspace), require_write=False
    )

    assert action == PermissionAction.ALLOW


@pytest.mark.parametrize("channel", ["web_chat", "desktop", "telegram", "cron"])
@pytest.mark.parametrize("relative", [".git/hooks/pre-commit", ".git/config"])
def test_no_channel_preset_lets_the_write_through(workspace: Path, channel: str, relative: str) -> None:
    config = build_channel_security_config(channel, None, local_mode=True)

    action, _ = evaluate_tool_call(
        "file_write",
        {"file_path": str(workspace / relative), "content": "#!/bin/sh\n"},
        config,
        workspace_root=str(workspace),
        tool_name="file_write_tool",
    )

    assert action != PermissionAction.ALLOW
