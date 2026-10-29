"""Tests for workspace rules injection middleware."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ExtendedModelResponse, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from myrm_agent_harness.agent.workspace_rules.middleware import (
    SNAPSHOT_KEY,
    SNAPSHOT_ROOT_KEY,
    WorkspaceContextState,
    WorkspaceRulesMiddleware,
    _find_workspace_insert_idx,
    _format_rules_content,
)
from myrm_agent_harness.agent.workspace_rules.scanner import RuleFile


class TestFindWorkspaceInsertIdx:
    def test_after_system_messages(self) -> None:
        messages = [
            SystemMessage(content="System prompt"),
            SystemMessage(content="User instructions"),
            HumanMessage(content="Hello"),
        ]
        assert _find_workspace_insert_idx(messages) == 2

    def test_no_system_messages(self) -> None:
        messages = [HumanMessage(content="Hello")]
        assert _find_workspace_insert_idx(messages) == 0

    def test_all_system_messages(self) -> None:
        messages = [
            SystemMessage(content="A"),
            SystemMessage(content="B"),
            SystemMessage(content="C"),
        ]
        assert _find_workspace_insert_idx(messages) == 3

    def test_empty_messages(self) -> None:
        assert _find_workspace_insert_idx([]) == 0


class TestFormatRulesContent:
    def test_formats_single_rule(self) -> None:
        rules = [RuleFile(path="/project/AGENTS.md", content="# Rules\nDo X.", source="AGENTS.md")]
        result = _format_rules_content(rules)
        assert "<workspace_context" in result
        assert "AGENTS.md" in result
        assert "# Rules" in result
        assert "</workspace_context>" in result

    def test_formats_multiple_rules(self) -> None:
        rules = [
            RuleFile(path="/project/.myrm/rules/a.md", content="Rule A", source=".myrm/rules"),
            RuleFile(path="/project/SOUL.md", content="Rule B", source="SOUL.md"),
        ]
        result = _format_rules_content(rules)
        assert "a.md" in result
        assert "SOUL.md" in result
        assert "Rule A" in result
        assert "Rule B" in result

    def test_skips_non_rulefile_objects(self) -> None:
        rules = [MagicMock(), RuleFile(path="/project/X.md", content="Valid", source="X.md")]
        result = _format_rules_content(rules)
        assert "Valid" in result

    def test_empty_rules(self) -> None:
        result = _format_rules_content([])
        assert "<workspace_context" in result
        assert "</workspace_context>" in result


_GATE = "myrm_agent_harness.agent.security.workspace_trust.gate.blocks_workspace_side_channels"
_GENERATE = "myrm_agent_harness.toolkits.code_execution.sandbox_snapshot.generate_sandbox_bootstrap_snapshot"


def _runtime(workspace: object) -> MagicMock:
    runtime = MagicMock()
    runtime.context = {"workspace_path": str(workspace)}
    return runtime


def _holding(root: object) -> WorkspaceContextState:
    return WorkspaceContextState(messages=[], workspace_snapshot="<held/>", workspace_snapshot_root=str(root))


def _request(workspace: object, state: WorkspaceContextState) -> MagicMock:
    request = MagicMock()
    request.messages = [SystemMessage(content="System"), HumanMessage(content="Hello")]
    request.state = state
    request.runtime = _runtime(workspace)
    request.override = MagicMock(return_value=request)
    return request


def _sent(request: MagicMock) -> str:
    """The workspace context message the model call was sent: it follows the leading system prompt."""
    return str(request.override.call_args[1]["messages"][1].content)


def _response() -> ModelResponse:
    return ModelResponse(result=[AIMessage(content="ok")])


class TestWorkspaceRulesMiddleware:
    def test_sync_wrap_passes_through(self) -> None:
        mw = WorkspaceRulesMiddleware()
        response = MagicMock()
        handler = MagicMock(return_value=response)
        request = MagicMock()
        result = mw.wrap_model_call(request, handler)
        handler.assert_called_once_with(request)
        assert result is response

    @pytest.mark.asyncio
    async def test_skips_when_no_workspace_root(self) -> None:
        mw = WorkspaceRulesMiddleware()
        handler = AsyncMock()

        request = MagicMock()
        request.messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        request.state = {"messages": []}
        request.runtime = MagicMock()
        request.runtime.context = {}

        with patch(
            "myrm_agent_harness.agent.workspace_rules.middleware.WorkspaceRulesMiddleware._resolve_workspace_root",
            return_value="",
        ):
            await mw.awrap_model_call(request, handler)

        handler.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_skips_when_no_rules_found(self, tmp_path: Path) -> None:
        mw = WorkspaceRulesMiddleware()
        handler = AsyncMock()

        (tmp_path / ".git").mkdir()

        request = MagicMock()
        request.messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Hello"),
        ]
        request.state = {"messages": []}
        request.override = MagicMock(return_value=request)

        with patch(
            "myrm_agent_harness.agent.workspace_rules.middleware.WorkspaceRulesMiddleware._resolve_workspace_root",
            return_value=str(tmp_path),
        ):
            await mw.awrap_model_call(request, handler)

        handler.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_injects_rules(self, tmp_path: Path) -> None:
        mw = WorkspaceRulesMiddleware()
        handler = AsyncMock()

        (tmp_path / ".git").mkdir()
        (tmp_path / "AGENTS.md").write_text("# Project Rules\nUse type hints.")

        request = MagicMock()
        request.messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
        ]
        request.state = _holding(tmp_path)
        request.override = MagicMock(return_value=request)

        with (
            patch(
                "myrm_agent_harness.agent.workspace_rules.middleware.WorkspaceRulesMiddleware._resolve_workspace_root",
                return_value=str(tmp_path),
            ),
            patch(
                "myrm_agent_harness.agent.security.workspace_trust.gate.blocks_workspace_side_channels",
                return_value=False,
            ),
        ):
            await mw.awrap_model_call(request, handler)

        request.override.assert_called_once()
        injected = request.override.call_args[1]["messages"]
        workspace_msgs = [m for m in injected if isinstance(m, SystemMessage) and "<workspace_context" in m.content]
        assert len(workspace_msgs) == 1
        assert "Project Rules" in workspace_msgs[0].content
        assert "<held/>" in workspace_msgs[0].content


class TestSnapshotCapture:
    @pytest.mark.asyncio
    async def test_the_first_call_of_a_thread_takes_the_snapshot_and_hands_it_to_the_state(
        self, tmp_path: Path
    ) -> None:
        response = _response()
        request = _request(tmp_path, WorkspaceContextState(messages=[]))
        with patch(_GATE, return_value=False):
            result = await WorkspaceRulesMiddleware().awrap_model_call(request, AsyncMock(return_value=response))

        assert isinstance(result, ExtendedModelResponse)
        assert result.model_response is response
        assert result.command is not None
        update = result.command.update
        assert isinstance(update, dict)
        assert update[SNAPSHOT_ROOT_KEY] == str(tmp_path)
        assert update[SNAPSHOT_KEY].startswith("<sandbox_environment_snapshot>")
        assert update[SNAPSHOT_KEY] in _sent(request), (
            "the call that takes the snapshot is sent what later calls read back"
        )

    @pytest.mark.asyncio
    async def test_the_snapshot_a_thread_holds_is_sent_and_nothing_is_taken(self, tmp_path: Path) -> None:
        response = _response()
        request = _request(tmp_path, _holding(tmp_path))
        with patch(_GATE, return_value=False), patch(_GENERATE) as generate:
            result = await WorkspaceRulesMiddleware().awrap_model_call(request, AsyncMock(return_value=response))

        assert result is response
        generate.assert_not_called()
        assert "<held/>" in _sent(request)

    @pytest.mark.asyncio
    async def test_a_changed_workspace_takes_a_new_snapshot(self, tmp_path: Path) -> None:
        other = tmp_path / "other"
        other.mkdir()
        request = _request(other, _holding(tmp_path))
        with patch(_GATE, return_value=False):
            result = await WorkspaceRulesMiddleware().awrap_model_call(request, AsyncMock(return_value=_response()))

        assert isinstance(result, ExtendedModelResponse)
        assert result.command is not None
        assert isinstance(result.command.update, dict)
        assert result.command.update[SNAPSHOT_ROOT_KEY] == str(other)
        assert "<held/>" not in _sent(request)

    @pytest.mark.asyncio
    async def test_a_workspace_the_trust_gate_blocks_is_not_probed_and_is_sent_unchanged(self, tmp_path: Path) -> None:
        response = _response()
        handler = AsyncMock(return_value=response)
        request = _request(tmp_path, WorkspaceContextState(messages=[]))
        with patch(_GATE, return_value=True), patch(_GENERATE) as generate:
            result = await WorkspaceRulesMiddleware().awrap_model_call(request, handler)

        assert result is response
        generate.assert_not_called()
        handler.assert_called_once_with(request)
        request.override.assert_not_called()

    @pytest.mark.asyncio
    async def test_without_a_workspace_root_nothing_is_probed(self) -> None:
        response = _response()
        request = _request("", WorkspaceContextState(messages=[]))
        with (
            patch.object(WorkspaceRulesMiddleware, "_resolve_workspace_root", return_value=""),
            patch(_GENERATE) as generate,
        ):
            result = await WorkspaceRulesMiddleware().awrap_model_call(request, AsyncMock(return_value=response))

        assert result is response
        generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_failed_probe_stores_nothing_so_the_next_call_tries_again(self, tmp_path: Path) -> None:
        response = _response()
        request = _request(tmp_path, WorkspaceContextState(messages=[]))
        with patch(_GATE, return_value=False), patch(_GENERATE, side_effect=OSError("probe failed")):
            result = await WorkspaceRulesMiddleware().awrap_model_call(request, AsyncMock(return_value=response))

        assert result is response, "no state update is handed back"


class TestResolveWorkspaceRoot:
    def test_from_runtime_context(self) -> None:
        request = MagicMock()
        request.runtime.context = {"workspace_path": "/project/root"}
        assert WorkspaceRulesMiddleware._resolve_workspace_root(request.runtime) == "/project/root"

    def test_falls_back_to_session_context(self) -> None:
        request = MagicMock()
        request.runtime.context = {}
        with patch(
            "myrm_agent_harness.agent.middlewares._session_context.get_workspace_root",
            return_value="/fallback/root",
        ):
            result = WorkspaceRulesMiddleware._resolve_workspace_root(request.runtime)
        assert result == "/fallback/root"

    def test_none_runtime(self) -> None:
        request = MagicMock()
        request.runtime = None
        with patch(
            "myrm_agent_harness.agent.middlewares._session_context.get_workspace_root",
            return_value="",
        ):
            result = WorkspaceRulesMiddleware._resolve_workspace_root(request.runtime)
        assert result == ""

    def test_non_dict_context(self) -> None:
        request = MagicMock()
        request.runtime.context = "not_a_dict"
        with patch(
            "myrm_agent_harness.agent.middlewares._session_context.get_workspace_root",
            return_value="/session/root",
        ):
            result = WorkspaceRulesMiddleware._resolve_workspace_root(request.runtime)
        assert result == "/session/root"

    def test_empty_workspace_path(self) -> None:
        request = MagicMock()
        request.runtime.context = {"workspace_path": ""}
        with patch(
            "myrm_agent_harness.agent.middlewares._session_context.get_workspace_root",
            return_value="/session/root",
        ):
            result = WorkspaceRulesMiddleware._resolve_workspace_root(request.runtime)
        assert result == "/session/root"
