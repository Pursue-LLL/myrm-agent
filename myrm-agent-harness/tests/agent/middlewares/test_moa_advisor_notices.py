"""The advisor round starts on every user turn, and its advice is written once behind the message that was last.

The advice is a notice the runtime writes for the acting model, so the injectors behind the advisor middleware still
extend the user's own message, and every later request of the run carries the advice at the same place.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import create_moa_advisor_middleware
from myrm_agent_harness.core.message_origin import is_user_authored_human_message, runtime_human_message
from myrm_agent_harness.core.message_tail import append_block_to_last_user_message
from myrm_agent_harness.toolkits.llms.consensus.advisor_fanout import AdvisorFanoutRunner
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAFanoutMode, MoAOverlayConfig
from myrm_agent_harness.toolkits.llms.consensus.types import ReferenceResponse
from tests.support.completion_guard_harness import CountingModel, run_agent, writes_allowed

_MODULE = "myrm_agent_harness.agent.middlewares.moa_advisor_middleware"
_CALL = AIMessage(content="", tool_calls=[{"id": "c1", "name": "search", "args": {}}], id="ai1")
_RESULT = ToolMessage(content="found", tool_call_id="c1", id="t1")
_ADVICE = ReferenceResponse(model="ref-a", content="try the changelog first", elapsed_seconds=0.1, success=True)
_ADVICE_TEXT = "try the changelog first"


def _advisors(fanout: MoAFanoutMode = "user_turn") -> AgentMiddleware:
    return create_moa_advisor_middleware(
        [MagicMock(model_name="ref-a")], config=MoAOverlayConfig(min_successful=1, fanout=fanout)
    )


async def _sent(
    middleware: AgentMiddleware, messages: list[AnyMessage], *, run: dict[str, object] | None = None
) -> list[AnyMessage]:
    """The messages the acting model receives for ``messages``; requests sharing ``run`` belong to one run."""
    request = ModelRequest(
        messages=messages,
        model=MagicMock(model_name="acting"),
        runtime=Runtime(context=run) if run is not None else None,
    )
    handler = AsyncMock(return_value=ModelResponse(result=[]))
    with (
        patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock, return_value=[_ADVICE]),
        patch(f"{_MODULE}._emit_overlay_active", new_callable=AsyncMock),
    ):
        await middleware.awrap_model_call(request, handler)
    return list(handler.await_args.args[0].messages)


@pytest.mark.asyncio
async def test_the_advice_is_a_notice_of_the_runtime_behind_the_users_message() -> None:
    user = HumanMessage(content="question", id="u")

    sent = await _sent(_advisors(), [user])

    assert sent[0] is user
    assert user.content == "question"
    assert len(sent) == 2
    assert _ADVICE_TEXT in str(sent[1].content)
    assert isinstance(sent[1], HumanMessage)
    assert not is_user_authored_human_message(sent[1])


@pytest.mark.asyncio
async def test_a_notice_behind_the_users_message_is_kept_as_it_is() -> None:
    user = HumanMessage(content="question", id="u")
    notice = runtime_human_message("[restore] files")

    sent = await _sent(_advisors(), [user, notice])

    assert sent[0] is user
    assert any(message is notice for message in sent)
    assert notice.content == "[restore] files"
    assert not is_user_authored_human_message(notice)
    assert sum(_ADVICE_TEXT in str(message.content) for message in sent) == 1


@pytest.mark.asyncio
async def test_a_notice_behind_the_tool_results_is_kept_as_it_is() -> None:
    notice = runtime_human_message("[SYSTEM INSTRUCTION] cite every source")

    sent = await _sent(_advisors("per_iteration"), [HumanMessage(content="question", id="u"), _CALL, _RESULT, notice])

    assert sent[1:3] == [_CALL, _RESULT]
    assert any(message is notice for message in sent)
    assert notice.content == "[SYSTEM INSTRUCTION] cite every source"
    assert not is_user_authored_human_message(notice)
    assert sum(_ADVICE_TEXT in str(message.content) for message in sent) == 1


@pytest.mark.asyncio
async def test_the_advice_of_a_tool_loop_step_stands_behind_its_tool_result() -> None:
    sent = await _sent(_advisors("per_iteration"), [HumanMessage(content="question", id="u"), _CALL, _RESULT])

    advice = sent[-1]
    assert sent[1:3] == [_CALL, _RESULT]
    assert isinstance(advice, HumanMessage)
    assert _ADVICE_TEXT in str(advice.content)
    assert not is_user_authored_human_message(advice)


@pytest.mark.asyncio
async def test_the_injectors_behind_the_advisor_still_extend_the_users_own_message() -> None:
    sent = await _sent(_advisors("per_iteration"), [HumanMessage(content="question", id="u"), _CALL, _RESULT])

    placed = append_block_to_last_user_message(sent, "memory")

    assert placed[0].content == "question\n\nmemory"
    assert _ADVICE_TEXT in str(placed[-1].content)


@pytest.mark.asyncio
async def test_a_later_request_of_the_run_carries_the_advice_behind_the_same_message() -> None:
    advisors = _advisors()
    run: dict[str, object] = {}
    user = HumanMessage(content="question", id="u")

    first = await _sent(advisors, [user], run=run)
    later = await _sent(advisors, [user, _CALL, _RESULT], run=run)

    assert later[:2] == first
    assert later[2:] == [_CALL, _RESULT]


@pytest.mark.asyncio
async def test_a_notice_at_the_tail_of_the_first_request_does_not_move_the_advice_later() -> None:
    advisors = _advisors()
    run: dict[str, object] = {}
    user = HumanMessage(content="question", id="u")
    notice = runtime_human_message("[restore] files")

    first = await _sent(advisors, [user, notice], run=run)
    later = await _sent(advisors, [user, notice, _CALL, _RESULT], run=run)

    assert later[:3] == first
    assert later[3:] == [_CALL, _RESULT]


@pytest.mark.asyncio
async def test_the_advice_of_one_run_is_not_carried_into_the_next() -> None:
    advisors = _advisors()
    user = HumanMessage(content="question", id="u")
    await _sent(advisors, [user], run={})

    later_run = await _sent(advisors, [user, _CALL, _RESULT], run={})

    assert later_run == [user, _CALL, _RESULT]


@pytest.mark.asyncio
async def test_a_notice_behind_the_tool_results_starts_no_advisor_round() -> None:
    middleware = _advisors()
    messages = [HumanMessage(content="question", id="u"), _CALL, _RESULT, runtime_human_message("[notice]")]
    request = ModelRequest(messages=messages, model=MagicMock(model_name="acting"))
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    with (
        patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock, return_value=[_ADVICE]) as asked,
        patch(f"{_MODULE}._emit_overlay_active", new_callable=AsyncMock) as announced,
    ):
        await middleware.awrap_model_call(request, handler)

    asked.assert_not_called()
    announced.assert_not_called()
    handler.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_a_notice_behind_the_users_message_still_starts_the_advisor_round() -> None:
    middleware = _advisors()
    user = HumanMessage(content="question", id="u")
    request = ModelRequest(
        messages=[user, runtime_human_message("[restore] files")], model=MagicMock(model_name="acting")
    )
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    with (
        patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock, return_value=[_ADVICE]) as asked,
        patch(f"{_MODULE}._emit_overlay_active", new_callable=AsyncMock),
    ):
        await middleware.awrap_model_call(request, handler)

    assert asked.await_args is not None
    assert asked.await_args.args[0] == "question"


@pytest.mark.asyncio
async def test_every_turn_of_a_real_chat_gets_its_advisor_round_the_first_one_included(tmp_path: Path) -> None:
    # The whole chain is real. Behind the user's message, the first call of the chat carries the data-boundary
    # rules, the canary and the session directories as system messages.
    model = CountingModel(responses=[AIMessage(content="first answer"), AIMessage(content="second answer")])

    with (
        patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock, return_value=[_ADVICE]) as asked,
        patch(f"{_MODULE}._emit_overlay_active", new_callable=AsyncMock),
    ):
        await run_agent(
            tmp_path,
            writes_allowed(tmp_path),
            model,
            request="first question",
            then=["second question"],
            file_access_mode=FileAccessMode.FULL,
            enable_shell_tools=True,
            checkpointer=True,
            middlewares=[_advisors()],
        )

    assert asked.await_count == 2
    first_query, first_history = asked.await_args_list[0].args
    assert first_query.startswith("first question")
    assert not first_history
    second_query, second_history = asked.await_args_list[1].args
    assert second_query.startswith("second question")
    # What the first call added for the acting model alone (rules, canary, directories) never reaches an advisor.
    assert [type(message).__name__ for message in second_history] == ["HumanMessage", "AIMessage"]
    assert str(second_history[0].content).startswith("first question")

    first_request = model.transcripts[0]
    assert sum(isinstance(message, SystemMessage) for message in first_request) >= 3
    advisor = first_request[-1]
    assert isinstance(advisor, HumanMessage)
    assert _ADVICE_TEXT in str(advisor.content)
    assert not is_user_authored_human_message(advisor)
