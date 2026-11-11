"""Tests for SessionAccessMiddleware.

A run that holds a tool taking paths is told its directories exactly once per thread. A run that holds none (the
fast-search mount carries ``file_read_tool`` alone) is not, nor is a run without a config, with a message state that
is not a list, or whose history already carries the block. The registry is read when the hook runs, because it is
filled after the middleware chain is built. The whole-agent cases run the real mount, tool assembly and middleware
chain with only the model scripted.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares.session_access_middleware import (
    _SESSION_ACCESS_MARKER,
    SessionAccessMiddleware,
)
from myrm_agent_harness.agent.security.types import PathPolicy
from myrm_agent_harness.agent.tool_management import ToolSource
from myrm_agent_harness.core.message_origin import is_runtime_system_block
from tests.support.completion_guard_harness import (
    CountingModel,
    named_tool,
    registry_of,
    run_agent,
    writes_allowed,
)

_MODULE = "myrm_agent_harness.agent.middlewares.session_access_middleware"
_PATH_TOOLS = ("glob_tool", "grep_tool", "file_write_tool", "file_edit_tool", "bash_code_execute_tool")


def _make_config() -> SimpleNamespace:
    """A security config exposing `.path_policy` (the PathPolicy)."""
    return SimpleNamespace(path_policy=PathPolicy(access_roots=[]))


def _middleware(held: Sequence[str] = ("glob_tool",)) -> SessionAccessMiddleware:
    """The middleware of a run whose registry holds the named tools."""
    return SessionAccessMiddleware(registry_of([named_tool(name) for name in held]))


@pytest.fixture
def workspace_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """The session context of a run in a workspace: a config, a workspace root and a block to render."""
    monkeypatch.setattr(f"{_MODULE}.get_security_config", _make_config)
    monkeypatch.setattr(f"{_MODULE}.get_workspace_root", lambda: "/ws")
    monkeypatch.setattr(f"{_MODULE}.render_session_access_context", lambda *_: "- /ws [read-write]")


@pytest.mark.usefixtures("workspace_run")
class TestBeforeModel:
    def test_no_config_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(f"{_MODULE}.get_security_config", lambda: None)

        assert _middleware().before_model({"messages": []}, None) is None

    def test_empty_block_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(f"{_MODULE}.get_workspace_root", lambda: "")
        monkeypatch.setattr(f"{_MODULE}.render_session_access_context", lambda *_: "")

        assert _middleware().before_model({"messages": []}, None) is None

    def test_non_list_messages_returns_none(self) -> None:
        assert _middleware().before_model({"messages": "not-a-list"}, None) is None

    def test_injects_system_message_once(self) -> None:
        result = _middleware().before_model({"messages": [HumanMessage(content="hi")]}, None)

        assert result is not None
        messages = result["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], SystemMessage)
        assert _SESSION_ACCESS_MARKER in messages[0].content
        assert "</session-access>" in messages[0].content
        assert is_runtime_system_block(messages[0])

    def test_skips_when_marker_already_present(self) -> None:
        existing = SystemMessage(content=f"{_SESSION_ACCESS_MARKER}\nblock")

        assert _middleware().before_model({"messages": [HumanMessage(content="hi"), existing]}, None) is None


@pytest.mark.usefixtures("workspace_run")
class TestWhichRunsAreTold:
    @pytest.mark.parametrize("tool", _PATH_TOOLS)
    def test_a_run_holding_a_tool_that_takes_paths_is_told(self, tool: str) -> None:
        result = _middleware(["web_search_tool", tool]).before_model({"messages": []}, None)

        assert result is not None

    @pytest.mark.parametrize(
        "held",
        [(), ("file_read_tool",), ("file_read_tool", "web_search_tool", "todo_write", "bash_process_tool")],
        ids=["no tools", "spill and uploads reader", "reader with tools that take no paths"],
    )
    def test_a_run_holding_none_is_not_told(self, held: Sequence[str]) -> None:
        assert _middleware(held).before_model({"messages": []}, None) is None

    def test_the_registry_is_read_when_the_hook_runs(self) -> None:
        registry = registry_of([named_tool("file_read_tool")])
        middleware = SessionAccessMiddleware(registry)
        assert middleware.before_model({"messages": []}, None) is None

        registry.register(named_tool("glob_tool"), source=ToolSource.META)

        assert middleware.before_model({"messages": []}, None) is not None


class TestRealAgent:
    """Whole agent: the mount, tool assembly and middleware chain are real; only the model is scripted."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("file_access_mode", "enable_shell_tools", "told"),
        [
            (FileAccessMode.FULL, True, True),
            (FileAccessMode.WORKSPACE_READ_ONLY, False, True),
            (FileAccessMode.NONE, True, True),
            (FileAccessMode.SPILL_AND_UPLOADS, False, False),
            (FileAccessMode.NONE, False, False),
        ],
        ids=["full", "workspace read-only", "shell only", "spill and uploads (fast search)", "no file or shell tools"],
    )
    async def test_the_directories_reach_a_run_exactly_when_its_mount_takes_paths(
        self, tmp_path: Path, file_access_mode: FileAccessMode, enable_shell_tools: bool, told: bool
    ) -> None:
        model = CountingModel(responses=[AIMessage(content="hello")])

        await run_agent(
            tmp_path,
            writes_allowed(tmp_path),
            model,
            request="say hello",
            file_access_mode=file_access_mode,
            enable_shell_tools=enable_shell_tools,
        )

        systems = [str(message.content) for message in model.transcripts[0] if isinstance(message, SystemMessage)]
        assert any(_SESSION_ACCESS_MARKER in text for text in systems) is told
