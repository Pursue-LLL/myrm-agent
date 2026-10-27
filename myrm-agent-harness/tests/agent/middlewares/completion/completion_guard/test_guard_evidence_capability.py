"""The completion guard demands external evidence only from a run that could produce it.

A freshness question is held to an evidence step (web search or fetch, browser, MCP). A run holding none of
those tools can never meet the demand: the model repeats its answer for every rejection (one paid model call
each), even when it already says it cannot look anything up. For such a run the guard asks once for an honest
"could not be checked" and lets the answer through. The built-chain cases pin what ``build_middlewares`` reads
from the mounted tools; the ``create_skill_agent`` cases run the real tool assembly and run loop with only the
model scripted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.capabilities import CompletionCapabilities
from myrm_agent_harness.agent.middlewares.completion.completion_guard.directive import (
    BlockReasons,
    render_completion_directive,
)
from myrm_agent_harness.agent.tool_management import ToolSource
from tests.support.completion_guard_harness import (
    CountingModel,
    built_guard,
    named_tool,
    reasons_of,
    registry_of,
    run_agent,
    runtime,
    state,
    tool_names,
    verdict,
    writes_allowed,
)

_REQUEST = "今天最新的 AI 新闻是什么？"
_NOT_FRESH_REQUEST = "解释一下什么是向量数据库"
_FROM_MEMORY = "根据我所知，近期 AI 领域的主要进展包括多模态模型与推理能力的提升。"
_HONEST = "我这里没有联网检索工具，无法核实今天的最新新闻。以上内容来自训练数据，可能已过时。"
_FILE_TOOLS = ("file_read_tool", "glob_tool", "grep_tool")
_EVIDENCE_TOOLS = ("web_search_tool", "web_fetch_tool", "browser_navigate_tool", "mcp__news__latest")


class TestGuardDecision:
    """The guard's decision given what the run can gather; the capability itself is injected."""

    def setup_method(self) -> None:
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_a_run_that_cannot_gather_evidence_is_asked_once_to_say_so_and_then_let_through(
        self, tmp_path: Path
    ) -> None:
        guard = CompletionGuard(capabilities=CompletionCapabilities(can_gather_evidence=lambda: False))
        messages = state(_REQUEST, _FROM_MEMORY)

        first = reasons_of(await verdict(guard, messages, runtime(tmp_path)))
        assert first.evidence_unreachable is True
        assert "今天最新的 AI 新闻" in first.evidence
        assert await verdict(guard, messages, runtime(tmp_path)) is None

    @pytest.mark.asyncio
    async def test_a_run_that_can_gather_evidence_is_asked_until_the_rejection_budget_is_spent(
        self, tmp_path: Path
    ) -> None:
        guard = CompletionGuard(max_rejections=2)
        messages = state(_REQUEST, _FROM_MEMORY)

        assert not reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence_unreachable
        assert not reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence_unreachable
        assert reasons_of(await verdict(guard, messages, runtime(tmp_path))).forced_finish is True

    @pytest.mark.asyncio
    async def test_the_evidence_demand_is_dropped_but_another_critical_error_still_blocks(self, tmp_path: Path) -> None:
        guard = CompletionGuard(capabilities=CompletionCapabilities(can_gather_evidence=lambda: False))
        messages = state(_REQUEST, "我已经运行了测试，全部通过。今天的新闻如下。")

        first = reasons_of(await verdict(guard, messages, runtime(tmp_path)))
        second = reasons_of(await verdict(guard, messages, runtime(tmp_path)))

        assert first.evidence_unreachable is True
        assert second.evidence == ""
        assert second.execution_claim != ""


class TestDirectiveText:
    """What the model reads when the evidence demand cannot be met."""

    def test_it_is_asked_to_say_plainly_it_could_not_look_this_up(self) -> None:
        text = render_completion_directive(
            BlockReasons(evidence="latest user request hints external/freshness need: 'x'", evidence_unreachable=True),
            records=[],
            workspace_root=None,
        )

        assert "no tool" in text
        assert "out of date" in text
        assert "run at least one successful evidence step" not in text

    def test_a_run_that_can_gather_evidence_is_still_told_to_gather_it(self) -> None:
        text = render_completion_directive(
            BlockReasons(evidence="latest user request hints external/freshness need: 'x'"),
            records=[],
            workspace_root=None,
        )

        assert "run at least one successful evidence step" in text


class TestBuiltChainProbe:
    """What ``build_middlewares`` hands the guard: whether the mounted tools could produce evidence."""

    def setup_method(self) -> None:
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_a_run_without_an_evidence_tool_is_asked_once_and_then_let_through(self, tmp_path: Path) -> None:
        guard = built_guard(registry_of([named_tool(name) for name in _FILE_TOOLS]))
        messages = state(_REQUEST, _FROM_MEMORY)

        assert reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence_unreachable is True
        assert await verdict(guard, messages, runtime(tmp_path)) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evidence_tool", _EVIDENCE_TOOLS)
    async def test_a_run_with_an_evidence_tool_is_asked_again_until_the_evidence_is_there(
        self, tmp_path: Path, evidence_tool: str
    ) -> None:
        guard = built_guard(registry_of([named_tool("file_read_tool"), named_tool(evidence_tool)]))
        messages = state(_REQUEST, _FROM_MEMORY)

        assert reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence
        second = reasons_of(await verdict(guard, messages, runtime(tmp_path)))
        assert second.evidence
        assert not second.evidence_unreachable

    @pytest.mark.asyncio
    async def test_a_run_with_a_shell_keeps_being_asked_because_it_may_reach_an_mcp_server(
        self, tmp_path: Path
    ) -> None:
        guard = built_guard(registry_of([named_tool("bash_code_execute_tool")]))
        messages = state(_REQUEST, _FROM_MEMORY)

        assert not reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence_unreachable
        assert not reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence_unreachable

    @pytest.mark.asyncio
    async def test_the_tools_are_read_at_call_time_because_the_registry_is_filled_after_the_chain_is_built(
        self, tmp_path: Path
    ) -> None:
        registry = registry_of([])
        guard = built_guard(registry)
        messages = state(_REQUEST, _FROM_MEMORY)
        assert reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence_unreachable

        registry.register(named_tool("web_search_tool"), source=ToolSource.META)

        assert not reasons_of(await verdict(guard, messages, runtime(tmp_path))).evidence_unreachable

    @pytest.mark.asyncio
    async def test_a_question_without_a_freshness_hint_is_not_held_to_evidence(self, tmp_path: Path) -> None:
        guard = built_guard(registry_of([named_tool("file_read_tool")]))

        assert await verdict(guard, state(_NOT_FRESH_REQUEST, _FROM_MEMORY), runtime(tmp_path)) is None


class TestRealAgent:
    """Whole agent: tool assembly, middleware chain and run loop are real; only the model is scripted."""

    @pytest.mark.asyncio
    async def test_a_run_that_cannot_look_anything_up_answers_twice_not_five_times(self, tmp_path: Path) -> None:
        model = CountingModel(responses=[AIMessage(content=_FROM_MEMORY)], answer_after_check=_HONEST)

        agent, _ = await run_agent(
            tmp_path,
            writes_allowed(tmp_path),
            model,
            request=_REQUEST,
            file_access_mode=FileAccessMode.WORKSPACE_READ_ONLY,
            enable_shell_tools=False,
        )

        assert tool_names(agent) == set(_FILE_TOOLS)
        assert len(model.requests) == 2

    @pytest.mark.asyncio
    async def test_a_question_without_a_freshness_hint_is_answered_once(self, tmp_path: Path) -> None:
        model = CountingModel(responses=[AIMessage(content=_FROM_MEMORY)], answer_after_check=_HONEST)

        await run_agent(
            tmp_path,
            writes_allowed(tmp_path),
            model,
            request=_NOT_FRESH_REQUEST,
            file_access_mode=FileAccessMode.WORKSPACE_READ_ONLY,
            enable_shell_tools=False,
        )

        assert len(model.requests) == 1
