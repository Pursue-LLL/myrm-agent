"""Tests for the command workspace-path rewriter and the bash command preparation.

Covers the container-convention ``/workspace`` substitution (only where a shell takes it as a path of its own), the
guard that protects an already-resolved real workspace path (e.g. eval graders embedding ``{workspace}`` where the
cache layout ends in ``/workspace``) from being re-expanded into a duplicated path, and that a search command such as
grep reaches the shell as typed.
"""

import os
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.common.command_rewriter import (
    CommandRewriter,
)
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor

_WORKSPACE = "/data/agent/ws1"

# Commands that name the container-convention root: it becomes the real workspace wherever a shell takes it as a path.
_CONVENTION_ROOT_COMMANDS = [
    "cd /workspace && ls",
    "ls /workspace/src",
    "cd /workspace",
    "ls /workspace; pwd",
    "ls /workspace | head",
    'ls "/workspace"',
    "ls '/workspace'",
    'cat "/workspace/a b.txt"',
    "tool --dir=/workspace/x",
    "PATH=$PATH:/workspace/bin tool",
    "echo $(ls /workspace)",
    "cat >/workspace/out.txt",
    "echo hi>/workspace/f",
    "gcc -I/workspace/include a.c",
    "cmake -S/workspace -B/workspace/build",
    "tar -C/workspace -xf a.tar",
    "sed -i 's#old#/workspace/new#' f",
    "sed 's|a|/workspace/b|' f",
    "sed 's,a,/workspace/b,' f",
    "[ -d /workspace ] && echo ok",
    "x=$(cat /workspace/f)",
    "docker run -v /workspace:/data img",
    "cp a /workspace/",
    "ls -la /workspace/*.txt",
    "cd '/workspace/a b'",
]
# Paths that merely contain or start with the word: another directory, so the command stays as typed.
_OTHER_PATHS_NAMED_WORKSPACE = [
    "cd /Users/me/workspace/proj",
    "cat /home/dev/workspace/notes.txt",
    "ls ~/workspace",
    "ls ./workspace",
    "ls ../workspace/x",
    "ls ${HOME}/workspace",
    "ls $(pwd)/workspace",
    "ls /opt/workspace",
    "ls ~user/workspace",
    "ls a-b/workspace",
    "ls /workspace2",
    "ls /workspace.bak",
    "echo /workspace-old",
]
# A real workspace may hold a directory that is itself called workspace.
_REAL_WORKSPACE_SUBDIRECTORIES = [
    ("/tmp/ws", "ls /tmp/ws/workspace"),
    ("/tmp/ws", "cat /tmp/ws/workspace/a.txt"),
    ("/home/u/proj", "cd /home/u/proj/workspace && ls"),
    ("/data/x/workspace", "ls /data/x/workspace/workspace"),
]
_SEARCH_COMMANDS = [
    "grep -rEn 'foo|bar' .",
    "grep -rn --include='*.py' foo .",
    "grep -rn foo --exclude-dir=.git .",
    "grep -rhIL foo .",
    "grep '--pre=./payload.sh' -rn foo .",
    "dmesg -T | grep -iE 'oom[- ]killer|out of memory' | tail -n 20",
    "git grep -n foo",
    "command -v grep",
]


def _rewrite(command: str, workspace: str | None) -> str:
    rewriter = CommandRewriter()
    if workspace is None:
        return rewriter.rewrite_workspace_paths(command, None)
    return rewriter.rewrite_workspace_paths(command, Path(workspace))


class TestRewriteWorkspacePaths:
    def test_container_convention_replaced(self) -> None:
        assert _rewrite("cd /workspace && python3 main.py", "/tmp/ws") == ("cd /tmp/ws && python3 main.py")

    def test_path_arguments_replaced(self) -> None:
        assert _rewrite("cat /workspace/README.md", "/tmp/ws") == "cat /tmp/ws/README.md"

    def test_real_workspace_path_not_duplicated(self) -> None:
        """A real workspace ending in /workspace stays byte-identical."""
        ws = "/data/wb_bench/workspaces/code/t1/workspace"
        command = f"WORKSPACE={ws} LOG_DIR={ws}/.wb_bench/logs python3 {ws}/tests/verifier.py"
        assert _rewrite(command, ws) == command

    def test_mixed_real_and_convention_paths(self) -> None:
        ws = "/data/wb_bench/workspaces/code/t1/workspace"
        command = f"cd /workspace && echo {ws} > out.txt"
        assert _rewrite(command, ws) == f"cd {ws} && echo {ws} > out.txt"

    def test_no_workspace_path_returns_unchanged(self) -> None:
        assert _rewrite("echo hello", "/tmp/ws") == "echo hello"

    def test_none_workspace_returns_unchanged(self) -> None:
        assert _rewrite("echo hello", None) == "echo hello"


class TestWorkspaceRootBoundaries:
    @pytest.mark.parametrize("command", _CONVENTION_ROOT_COMMANDS)
    def test_the_convention_root_is_replaced(self, command: str) -> None:
        assert _rewrite(command, _WORKSPACE) == command.replace("/workspace", _WORKSPACE)

    @pytest.mark.parametrize("command", _OTHER_PATHS_NAMED_WORKSPACE)
    def test_another_path_named_workspace_is_left_alone(self, command: str) -> None:
        assert _rewrite(command, _WORKSPACE) == command

    @pytest.mark.parametrize(("workspace", "command"), _REAL_WORKSPACE_SUBDIRECTORIES)
    def test_a_directory_named_workspace_inside_the_real_workspace_is_left_alone(
        self, workspace: str, command: str
    ) -> None:
        assert _rewrite(command, workspace) == command


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in ripgrep is a shell script")
class TestBashCommandPreparation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", _SEARCH_COMMANDS)
    async def test_a_search_command_reaches_the_shell_as_typed(
        self, command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Approval and validation judged exactly this program: grep with ``--pre`` is read-only, ripgrep's runs it."""
        stand_in = tmp_path / "bin" / "rg"
        stand_in.parent.mkdir()
        stand_in.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stand_in.chmod(0o755)
        monkeypatch.setenv("PATH", f"{stand_in.parent}{os.pathsep}{os.environ.get('PATH', '')}")
        executor = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))

        assert await executor._prepare_bash_command(command) == command
