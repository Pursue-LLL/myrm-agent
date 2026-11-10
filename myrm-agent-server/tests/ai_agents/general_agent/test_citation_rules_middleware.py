"""Tests for citation_rules_middleware — the notice is a pure function of the history, so every request extends the last."""

from __future__ import annotations

import importlib
import itertools
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.runtime import Runtime
from myrm_agent_harness.core.message_origin import is_user_authored_human_message, runtime_human_message
from pydantic import Field

from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
    CitationRulesMiddleware,
    _end_of_first_source_group,
    citation_rules_middleware,
)

# The package re-exports the middleware instance under the module's name, so the module is imported by its path.
citation_rules_module = importlib.import_module("app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware")

_SOURCE = "<<<UNTRUSTED_DATA web_search>>>\nPython is a language\n<<<END_UNTRUSTED_DATA>>>"


def _call(call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "web_search_tool", "args": {}, "id": call_id}])


def _result(call_id: str, content: str = _SOURCE) -> ToolMessage:
    return ToolMessage(content=content, tool_call_id=call_id, name="web_search_tool")


async def _sent(messages: list[AnyMessage], context: dict[str, object] | None = None) -> list[AnyMessage]:
    """The messages the middleware hands to the model for a request over ``messages``."""
    handler = AsyncMock(return_value=ModelResponse(result=[]))
    request = ModelRequest(
        model=AsyncMock(),
        messages=messages,
        runtime=Runtime(context=context) if context is not None else None,
    )
    await CitationRulesMiddleware().awrap_model_call(request, handler)
    call = handler.await_args
    assert call is not None
    return call.args[0].messages


def _notices(messages: list[AnyMessage]) -> list[int]:
    return [i for i, m in enumerate(messages) if "[SYSTEM INSTRUCTION]" in str(m.content)]


class TestEndOfFirstSourceGroup:
    def test_detects_the_untrusted_marker(self) -> None:
        assert _end_of_first_source_group([HumanMessage(content="query"), _call("c1"), _result("c1")]) == 2

    def test_no_marker(self) -> None:
        assert _end_of_first_source_group([HumanMessage(content="query"), _call("c1"), _result("c1", "clean result")]) == -1

    def test_no_user_message_means_no_turn(self) -> None:
        assert _end_of_first_source_group([_result("c1")]) == -1

    def test_only_the_current_turn_is_scanned(self) -> None:
        messages = [
            HumanMessage(content="search web"),
            _call("c0"),
            _result("c0"),
            AIMessage(content="previous answer"),
            HumanMessage(content="now calculate 2+2"),
            _call("c1"),
            _result("c1", "4"),
        ]

        assert _end_of_first_source_group(messages) == -1

    def test_a_runtime_notice_does_not_start_a_new_turn(self) -> None:
        messages = [
            HumanMessage(content="search web"),
            runtime_human_message("[restore] files were restored"),
            _call("c0"),
            _result("c0"),
        ]

        assert _end_of_first_source_group(messages) == 3

    def test_the_group_ends_after_the_last_result_of_the_call(self) -> None:
        messages = [
            HumanMessage(content="query"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "web_search_tool", "args": {}, "id": "a"},
                    {"name": "web_search_tool", "args": {}, "id": "b"},
                    {"name": "calculator", "args": {}, "id": "c"},
                ],
            ),
            _result("a", "clean"),
            _result("b"),
            _result("c", "4"),
            AIMessage(content="next"),
        ]

        assert _end_of_first_source_group(messages) == 4

    def test_multimodal_results_are_not_sources(self) -> None:
        result = ToolMessage(content=[{"type": "text", "text": _SOURCE}], tool_call_id="c1", name="web_search_tool")

        assert _end_of_first_source_group([HumanMessage(content="query"), _call("c1"), result]) == -1


class TestCitationRulesMiddleware:
    @pytest.mark.asyncio
    async def test_the_notice_stands_behind_the_tool_results_that_brought_the_source(self) -> None:
        sent = await _sent([SystemMessage(content="sys"), HumanMessage(content="user query"), _call("c1"), _result("c1")])

        assert _notices(sent) == [4]
        assert isinstance(sent[4], HumanMessage)
        assert not is_user_authored_human_message(sent[4])

    @pytest.mark.asyncio
    async def test_the_notice_stays_where_it_was_written_when_the_loop_goes_on(self) -> None:
        sent = await _sent(
            [
                HumanMessage(content="query"),
                _call("c1"),
                _result("c1"),
                AIMessage(content="running code"),
                ToolMessage(content="table output", tool_call_id="c2", name="bash_code_execute_tool"),
            ]
        )

        assert _notices(sent) == [3]
        assert sent[-1].content == "table output"

    @pytest.mark.asyncio
    async def test_the_notice_follows_every_result_of_a_parallel_call(self) -> None:
        messages: list[AnyMessage] = [
            HumanMessage(content="query"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "web_search_tool", "args": {}, "id": "a"},
                    {"name": "web_search_tool", "args": {}, "id": "b"},
                ],
            ),
            _result("a"),
            _result("b"),
        ]

        sent = await _sent(messages)

        assert _notices(sent) == [4]
        assert [m.type for m in sent[:4]] == ["human", "ai", "tool", "tool"]

    @pytest.mark.asyncio
    async def test_every_request_of_the_run_extends_the_one_before_it(self) -> None:
        """The provider caches the prefix and binds reasoning blocks to it, so no request may rewrite an earlier one."""
        history: list[AnyMessage] = [HumanMessage(content="query", id="u1"), _call("c1"), _result("c1")]
        context: dict[str, object] = {"prompt_mode": "full"}
        requests: list[list[AnyMessage]] = []
        for step in range(3):
            requests.append(await _sent(list(history), context))
            history += [AIMessage(content=f"step {step}", id=f"a{step}"), _call(f"d{step}"), _result(f"d{step}", "clean")]

        for earlier, later in itertools.pairwise(requests):
            assert later[: len(earlier)] == earlier
        assert all(len(_notices(sent)) == 1 for sent in requests)

    @pytest.mark.asyncio
    async def test_the_request_the_middleware_was_given_is_not_mutated(self) -> None:
        messages: list[AnyMessage] = [HumanMessage(content="query"), _call("c1"), _result("c1")]

        await _sent(messages)

        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_noop_when_no_untrusted_source(self) -> None:
        messages: list[AnyMessage] = [SystemMessage(content="sys"), HumanMessage(content="query")]

        assert await _sent(messages) == messages

    @pytest.mark.asyncio
    async def test_noop_when_the_run_has_no_citation_rules(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(citation_rules_module, "get_citation_rules_if_needed", lambda needed, locale=None: "")
        messages: list[AnyMessage] = [HumanMessage(content="query"), _call("c1"), _result("c1")]

        assert await _sent(messages) == messages

    def test_the_sync_path_hands_the_request_on_untouched(self) -> None:
        request = ModelRequest(model=AsyncMock(), messages=[HumanMessage(content="query")], runtime=None)
        response = ModelResponse(result=[])
        handler = MagicMock(return_value=response)

        assert CitationRulesMiddleware().wrap_model_call(request, handler) is response
        handler.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_noop_without_a_user_message(self) -> None:
        messages: list[AnyMessage] = [runtime_human_message("[restore] notice"), _call("c1"), _result("c1")]

        assert await _sent(messages) == messages

    @pytest.mark.asyncio
    async def test_a_source_of_an_earlier_turn_does_not_trigger_the_rules(self) -> None:
        messages: list[AnyMessage] = [
            HumanMessage(content="search web"),
            _call("c0"),
            _result("c0"),
            AIMessage(content="previous answer"),
            HumanMessage(content="now calculate 2+2"),
        ]

        assert await _sent(messages) == messages

    @pytest.mark.asyncio
    async def test_no_system_message_is_added(self) -> None:
        sent = await _sent([SystemMessage(content="sys"), HumanMessage(content="query"), _call("c1"), _result("c1")])

        assert [m.content for m in sent if isinstance(m, SystemMessage)] == ["sys"]

    @pytest.mark.asyncio
    async def test_skips_injection_in_search_mode(self) -> None:
        messages: list[AnyMessage] = [HumanMessage(content="query"), _call("c1"), _result("c1")]

        assert await _sent(messages, {"prompt_mode": "search"}) == messages

    @pytest.mark.asyncio
    async def test_injects_in_full_mode(self) -> None:
        sent = await _sent([HumanMessage(content="query"), _call("c1"), _result("c1")], {"prompt_mode": "full"})

        assert _notices(sent) == [3]

    @pytest.mark.asyncio
    async def test_injects_zh_rules_when_prompt_locale_zh(self) -> None:
        sent = await _sent(
            [HumanMessage(content="query"), _call("c1"), _result("c1")],
            {"prompt_mode": "full", "prompt_locale": "zh-CN"},
        )

        assert "【任务完整性提醒】" in str(sent[3].content)

    @pytest.mark.asyncio
    async def test_injects_en_rules_without_a_locale(self) -> None:
        sent = await _sent([HumanMessage(content="query"), _call("c1"), _result("c1")])

        assert "[TASK INTEGRITY REMINDER]" in str(sent[3].content)

    @pytest.mark.asyncio
    async def test_the_same_history_always_gives_the_same_notice(self) -> None:
        messages: list[AnyMessage] = [HumanMessage(content="query"), _call("c1"), _result("c1")]

        assert await _sent(messages) == await _sent(messages)


class _ScriptedModel(BaseChatModel):
    """Answers from a script and records the ``(type, text)`` of every message each call was sent."""

    script: list[AIMessage]
    calls: list[list[tuple[str, str]]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.calls.append([(type(m).__name__, str(m.content)) for m in messages])
        return ChatResult(generations=[ChatGeneration(message=self.script[len(self.calls) - 1])])


@tool
def web_search_tool() -> str:
    """Search the web."""
    return _SOURCE


class TestInACompiledLoop:
    @pytest.mark.asyncio
    async def test_the_rules_stand_behind_the_first_results_and_every_request_extends_the_one_before(self) -> None:
        model = _ScriptedModel(
            script=[
                AIMessage(content="", tool_calls=[{"id": "c1", "name": "web_search_tool", "args": {}}]),
                AIMessage(content="", tool_calls=[{"id": "c2", "name": "web_search_tool", "args": {}}]),
                AIMessage(content="answer"),
            ]
        )
        graph = create_agent(model, tools=[web_search_tool], middleware=[citation_rules_middleware])

        await graph.ainvoke({"messages": [HumanMessage(content="what is python")]})

        first, second, third = model.calls
        marked = [i for i, (_, text) in enumerate(third) if "[SYSTEM INSTRUCTION]" in text]
        assert not any("[SYSTEM INSTRUCTION]" in text for _, text in first), "no source has been read yet"
        assert [i for i, (_, text) in enumerate(second) if "[SYSTEM INSTRUCTION]" in text] == [3]
        assert marked == [3], "a second search does not move or repeat the rules"
        assert second[: len(first)] == first
        assert third[: len(second)] == second
        assert third[3][0] == "HumanMessage"
