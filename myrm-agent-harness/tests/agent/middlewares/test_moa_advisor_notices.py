"""The advisor round starts on every user turn, and its block is written so that the user's own message stays the one
the injectors behind it extend."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
    _inject_advisor_block_cache_safe,
    create_moa_advisor_middleware,
)
from myrm_agent_harness.core.message_origin import is_user_authored_human_message, runtime_human_message
from myrm_agent_harness.core.message_tail import append_block_to_last_user_message
from myrm_agent_harness.toolkits.llms.consensus.advisor_fanout import AdvisorFanoutRunner
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAOverlayConfig
from myrm_agent_harness.toolkits.llms.consensus.types import ReferenceResponse
from tests.support.completion_guard_harness import CountingModel, run_agent, writes_allowed

_MODULE = "myrm_agent_harness.agent.middlewares.moa_advisor_middleware"
_CALL = AIMessage(content="", tool_calls=[{"id": "c1", "name": "search", "args": {}}], id="ai1")
_RESULT = ToolMessage(content="found", tool_call_id="c1", id="t1")
_ADVICE = ReferenceResponse(model="ref-a", content="try the changelog first", elapsed_seconds=0.1, success=True)


def test_a_notice_behind_the_users_message_is_kept_and_the_advisor_block_follows_it() -> None:
    user = HumanMessage(content="question", id="u")
    notice = runtime_human_message("[restore] files")

    injected = _inject_advisor_block_cache_safe([user, notice], "advice")

    assert len(injected) == 3
    assert injected[0] is user
    assert injected[1] is notice
    advisor = injected[2]
    assert isinstance(advisor, HumanMessage)
    assert advisor.content == "advice"
    assert not is_user_authored_human_message(advisor)


def test_a_notice_behind_the_tool_results_keeps_its_text_and_its_provenance() -> None:
    notice = runtime_human_message("[SYSTEM INSTRUCTION] cite every source")

    injected = _inject_advisor_block_cache_safe([HumanMessage(content="question"), _CALL, _RESULT, notice], "advice")

    assert injected[3] is notice
    assert notice.content == "[SYSTEM INSTRUCTION] cite every source"
    assert not is_user_authored_human_message(notice)
    advisor = injected[4]
    assert isinstance(advisor, HumanMessage)
    assert advisor.content == "advice"
    assert not is_user_authored_human_message(advisor)


@pytest.mark.parametrize(
    "messages",
    [[], [HumanMessage(content="question", id="u"), _CALL, _RESULT]],
    ids=["empty-request", "tool-loop"],
)
def test_the_advisor_block_of_a_request_without_a_fresh_user_message_is_the_runtimes(
    messages: list[AnyMessage],
) -> None:
    injected = _inject_advisor_block_cache_safe(messages, "advice")

    advisor = injected[-1]
    assert isinstance(advisor, HumanMessage)
    assert advisor.content == "advice"
    assert not is_user_authored_human_message(advisor)


def test_the_injectors_behind_the_advisor_still_extend_the_users_own_message() -> None:
    user = HumanMessage(content="question", id="u")
    injected = _inject_advisor_block_cache_safe([user, _CALL, _RESULT], "advice")

    placed = append_block_to_last_user_message(injected, "memory")

    assert placed[0].content == "question\n\nmemory"
    assert placed[-1].content == "advice"


@pytest.mark.asyncio
async def test_a_notice_behind_the_tool_results_starts_no_advisor_round() -> None:
    middleware = create_moa_advisor_middleware(
        [MagicMock(model_name="ref-a")], config=MoAOverlayConfig(min_successful=1, fanout="user_turn")
    )
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
    middleware = create_moa_advisor_middleware(
        [MagicMock(model_name="ref-a")], config=MoAOverlayConfig(min_successful=1, fanout="user_turn")
    )
    user = HumanMessage(content="question", id="u")
    notice = runtime_human_message("[restore] files")
    request = ModelRequest(messages=[user, notice], model=MagicMock(model_name="acting"))
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    with (
        patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock, return_value=[_ADVICE]) as asked,
        patch(f"{_MODULE}._emit_overlay_active", new_callable=AsyncMock),
    ):
        await middleware.awrap_model_call(request, handler)

    assert asked.await_args is not None
    assert asked.await_args.args[0] == "question"
    assert handler.await_args is not None
    sent = handler.await_args.args[0].messages
    assert sent[0] is user
    assert sent[1] is notice
    assert "try the changelog first" in str(sent[2].content)
    assert not is_user_authored_human_message(sent[2])


@pytest.mark.asyncio
async def test_every_turn_of_a_real_chat_gets_its_advisor_round_the_first_one_included(tmp_path: Path) -> None:
    # The whole chain is real. Behind the user's message, the first call of the chat carries the data-boundary
    # rules, the canary and the session directories as system messages.
    model = CountingModel(responses=[AIMessage(content="first answer"), AIMessage(content="second answer")])
    middleware = create_moa_advisor_middleware(
        [MagicMock(model_name="ref-a")], config=MoAOverlayConfig(min_successful=1, fanout="user_turn")
    )

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
            middlewares=[middleware],
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
    assert "try the changelog first" in str(advisor.content)
    assert not is_user_authored_human_message(advisor)
