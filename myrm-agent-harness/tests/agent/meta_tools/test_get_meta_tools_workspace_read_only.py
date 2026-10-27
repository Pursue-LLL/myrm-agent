"""get_meta_tools mounts only the readable half of the workspace tools for WORKSPACE_READ_ONLY."""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool

import myrm_agent_harness.agent.meta_tools as meta_tools
from myrm_agent_harness.agent.meta_tools import get_meta_tools
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry

_SHELL_TOOLS = ["bash_code_execute_tool", "bash_process_tool"]


def _mounted(mode: FileAccessMode, *, with_shell: bool = False) -> list[BaseTool]:
    return get_meta_tools(
        [],
        skill_backend=None,
        registry=ToolRegistry(),
        file_access_mode=mode,
        enable_shell_tools=with_shell,
    )


def _names(mode: FileAccessMode, *, with_shell: bool = False) -> list[str]:
    return [tool.name for tool in _mounted(mode, with_shell=with_shell)]


def test_workspace_read_only_mounts_read_glob_and_grep_only() -> None:
    assert _names(FileAccessMode.WORKSPACE_READ_ONLY) == ["file_read_tool", "glob_tool", "grep_tool"]


def test_workspace_read_only_keeps_shell_independent_of_file_mode() -> None:
    """A verifier reads the workspace and runs commands, so the shell flag decides the shell tools."""
    assert _names(FileAccessMode.WORKSPACE_READ_ONLY, with_shell=True) == [
        "file_read_tool",
        "glob_tool",
        "grep_tool",
        *_SHELL_TOOLS,
    ]


def test_workspace_read_only_file_read_is_not_limited_to_evicted_and_uploaded_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlike SPILL_AND_UPLOADS, a read-only child reads the whole workspace."""
    path_policies: list[str] = []
    real_create = meta_tools.create_file_read_tool

    def spy(*args: object, **kwargs: object) -> BaseTool:
        path_policies.append(str(kwargs.get("path_policy", "full")))
        return real_create(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(meta_tools, "create_file_read_tool", spy)

    _mounted(FileAccessMode.WORKSPACE_READ_ONLY)
    _mounted(FileAccessMode.SPILL_AND_UPLOADS)

    assert path_policies == ["full", "evicted_uploaded"]


def test_full_mount_order_is_unchanged() -> None:
    """The tool order is part of the cached prompt prefix, so adding a mode must not reorder FULL."""
    assert _names(FileAccessMode.FULL, with_shell=True) == [
        "file_read_tool",
        "file_write_tool",
        "file_edit_tool",
        "glob_tool",
        "grep_tool",
        *_SHELL_TOOLS,
    ]
