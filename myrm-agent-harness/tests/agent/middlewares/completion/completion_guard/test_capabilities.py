"""``capabilities_of`` reads what a run can do from its registry and policy, at the time of each question.

The completion guard holds a run to a demand only when the run could meet it: keep a todo list (needs
``todo_write``), save a deliverable (needs ``file_write_tool`` and a policy that allows ``file_write``), gather
external evidence (needs a web, browser or MCP tool, or a shell that may reach an MCP server). The registry is
filled after the middleware chain is built, so each answer is read when asked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.middlewares._session_context import set_security_config
from myrm_agent_harness.agent.middlewares.completion.completion_guard.capabilities import (
    CompletionCapabilities,
    capabilities_of,
)
from myrm_agent_harness.agent.tool_management import ToolSource
from myrm_agent_harness.core.security.types import SecurityConfig
from tests.support.completion_guard_harness import (
    named_tool,
    registry_of,
    runtime,
    writes_allowed,
    writes_denied,
)

_EVIDENCE_TOOLS = (
    "web_search_tool",
    "web_fetch_tool",
    "browser_navigate_tool",
    "browser_extract_tool",
    "browser_snapshot_tool",
    "browser_inspect_tool",
    "mcp__news__latest",
    "bash_code_execute_tool",
)
_NOT_EVIDENCE_TOOLS = ("file_read_tool", "file_write_tool", "glob_tool", "grep_tool", "todo_write", "_internal_tool")


def test_a_run_with_no_declared_limits_is_held_to_every_demand(tmp_path: Path) -> None:
    capabilities = CompletionCapabilities()

    assert capabilities.keeps_todo_list() is True
    assert capabilities.can_save_files(runtime(tmp_path)) is True
    assert capabilities.can_gather_evidence() is True


class TestTodoList:
    def test_a_run_keeps_a_todo_list_only_when_it_holds_todo_write(self) -> None:
        registry = registry_of([named_tool("file_read_tool")])
        capabilities = capabilities_of(registry)
        assert capabilities.keeps_todo_list() is False

        registry.register(named_tool("todo_write"), source=ToolSource.META)

        assert capabilities.keeps_todo_list() is True


class TestEvidence:
    @pytest.mark.parametrize("evidence_tool", _EVIDENCE_TOOLS)
    def test_a_run_holding_a_tool_that_can_produce_evidence_can_gather_it(self, evidence_tool: str) -> None:
        capabilities = capabilities_of(registry_of([named_tool("file_read_tool"), named_tool(evidence_tool)]))

        assert capabilities.can_gather_evidence() is True

    @pytest.mark.parametrize("other_tool", _NOT_EVIDENCE_TOOLS)
    def test_a_run_holding_nothing_that_can_produce_evidence_cannot_gather_it(self, other_tool: str) -> None:
        capabilities = capabilities_of(registry_of([named_tool(other_tool)]))

        assert capabilities.can_gather_evidence() is False

    def test_an_empty_run_cannot_gather_evidence_until_a_tool_is_registered(self) -> None:
        registry = registry_of([])
        capabilities = capabilities_of(registry)
        assert capabilities.can_gather_evidence() is False

        registry.register(named_tool("web_search_tool"), source=ToolSource.META)

        assert capabilities.can_gather_evidence() is True


class TestSavingFiles:
    def setup_method(self) -> None:
        set_security_config(None)

    def teardown_method(self) -> None:
        set_security_config(None)

    def test_a_run_without_the_write_tool_cannot_save_even_where_the_policy_allows_it(self, tmp_path: Path) -> None:
        capabilities = capabilities_of(registry_of([named_tool("file_read_tool")]))

        assert capabilities.can_save_files(runtime(tmp_path, writes_allowed(tmp_path))) is False

    def test_a_run_with_the_write_tool_and_no_known_policy_can_save(self, tmp_path: Path) -> None:
        capabilities = capabilities_of(registry_of([named_tool("file_write_tool")]))

        assert capabilities.can_save_files(runtime(tmp_path)) is True

    def test_a_policy_that_denies_file_write_stops_a_run_holding_the_write_tool(self, tmp_path: Path) -> None:
        capabilities = capabilities_of(registry_of([named_tool("file_write_tool")]))

        assert capabilities.can_save_files(runtime(tmp_path, writes_allowed(tmp_path))) is True
        assert capabilities.can_save_files(runtime(tmp_path, SecurityConfig.readonly())) is False
        assert capabilities.can_save_files(runtime(tmp_path, writes_denied(tmp_path))) is False

    def test_the_policy_bound_to_the_run_is_read_when_the_turn_snapshot_is_absent(self, tmp_path: Path) -> None:
        capabilities = capabilities_of(registry_of([named_tool("file_write_tool")]))
        set_security_config(SecurityConfig.readonly())

        assert capabilities.can_save_files(runtime(tmp_path)) is False
        assert capabilities.can_save_files(runtime(tmp_path, writes_allowed(tmp_path))) is True
