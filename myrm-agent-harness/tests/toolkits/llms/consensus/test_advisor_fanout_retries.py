"""What each advisor is sent, how a reference that fails is asked again, and a round nobody listens to."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, FunctionMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.toolkits.llms.consensus._history import flatten_tool_free_history
from myrm_agent_harness.toolkits.llms.consensus.advisor_fanout import AdvisorFanoutRunner, should_run_fanout
from myrm_agent_harness.toolkits.llms.consensus.advisor_prompts import ADVISOR_SYSTEM
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAFanoutMode, MoAOverlayConfig
from myrm_agent_harness.toolkits.llms.consensus.types import ReferenceResponse

_STREAM = "myrm_agent_harness.toolkits.llms.consensus.advisor_fanout.collect_stream"
_SLEEP = "myrm_agent_harness.toolkits.llms.consensus.advisor_fanout.asyncio.sleep"
_QUESTION = [HumanMessage(content="question")]


def _runner(fanout: MoAFanoutMode = "user_turn", retries: int = 1) -> AdvisorFanoutRunner:
    config = MoAOverlayConfig(fanout=fanout, max_retries_per_model=retries)
    return AdvisorFanoutRunner([MagicMock(model_name="ref-a")], config)


@pytest.mark.asyncio
async def test_each_advisor_is_sent_the_conversation_and_then_the_question() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="first"),
        AIMessage(content="answer"),
        HumanMessage(content="second"),
    ]

    with patch(_STREAM, new_callable=AsyncMock, return_value="advice") as stream:
        refs = await _runner().run(messages)

    assert [ref.content for ref in refs] == ["advice"]
    assert stream.await_args is not None
    sent = stream.await_args.args[1]
    assert [(type(message).__name__, message.content) for message in sent] == [
        ("SystemMessage", ADVISOR_SYSTEM),
        ("HumanMessage", "first"),
        ("AIMessage", "answer"),
        ("HumanMessage", "second"),
    ]


@pytest.mark.asyncio
async def test_a_state_asked_before_is_answered_from_the_cache_without_a_listener() -> None:
    runner = _runner(fanout="per_iteration")

    with patch(_STREAM, new_callable=AsyncMock, return_value="advice") as stream:
        first = await runner.run(_QUESTION)
        second = await runner.run(_QUESTION)

    assert second == first
    stream.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_empty_answer_is_asked_for_again_after_a_growing_pause() -> None:
    with (
        patch(_STREAM, new_callable=AsyncMock, side_effect=["", "  ", "advice"]) as stream,
        patch(_SLEEP, new_callable=AsyncMock) as pause,
    ):
        refs = await _runner(retries=3).run(_QUESTION)

    assert [ref.content for ref in refs] == ["advice"]
    assert stream.await_count == 3
    assert [call.args[0] for call in pause.await_args_list] == [2, 4]


@pytest.mark.asyncio
async def test_a_failed_attempt_is_asked_again_after_a_pause() -> None:
    with (
        patch(_STREAM, new_callable=AsyncMock, side_effect=[RuntimeError("overloaded"), "advice"]) as stream,
        patch(_SLEEP, new_callable=AsyncMock) as pause,
    ):
        refs = await _runner(retries=2).run(_QUESTION)

    assert [(ref.success, ref.content) for ref in refs] == [(True, "advice")]
    assert stream.await_count == 2
    pause.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_a_reference_that_answered_in_time_keeps_its_answer_when_another_runs_out_of_time() -> None:
    fast, slow = MagicMock(model_name="ref-fast"), MagicMock(model_name="ref-slow")
    runner = AdvisorFanoutRunner([fast, slow], MoAOverlayConfig(fanout="user_turn", timeout_total=0.05))

    async def answer(_self: AdvisorFanoutRunner, llm: MagicMock, _query: str, _history: object) -> ReferenceResponse:
        if llm is slow:
            await asyncio.sleep(10)
        return ReferenceResponse(model=llm.model_name, content="advice", elapsed_seconds=0.0, success=True)

    with patch.object(AdvisorFanoutRunner, "_query_single", answer):
        refs = await runner.run(_QUESTION)

    assert {(ref.model, ref.success) for ref in refs} == {("ref-fast", True), ("ref-slow", False)}
    assert {ref.error for ref in refs if not ref.success} == {"global timeout"}


def test_a_risk_triggered_round_runs_only_when_the_router_forces_it() -> None:
    def gate(*, force_run: bool) -> bool:
        return should_run_fanout(
            messages=_QUESTION, fanout="risk_triggered", every_n=2, iteration=1, force_run=force_run
        )

    assert gate(force_run=False) is False
    assert gate(force_run=True) is True


@pytest.mark.asyncio
async def test_a_user_message_without_text_gives_the_advisors_nothing_to_answer() -> None:
    image = HumanMessage(content=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}])

    with patch(_STREAM, new_callable=AsyncMock) as stream:
        assert await _runner(fanout="per_iteration").run([image]) == []

    stream.assert_not_called()


def test_the_history_keeps_only_what_an_advisor_without_tools_can_read() -> None:
    history: list[BaseMessage] = [
        HumanMessage(content="question"),
        SystemMessage(content="<memory-context>"),
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "search", "args": {}}]),
        ToolMessage(content="", tool_call_id="c1"),
        AIMessage(content="thinking aloud"),
        ToolMessage(content="x" * 700, tool_call_id="c2", name="search"),
        FunctionMessage(content="legacy function result", name="old_tool"),
    ]

    flat = flatten_tool_free_history(history)

    assert [str(message.content) for message in flat] == [
        "question",
        "<memory-context>",
        "thinking aloud",
        f"[search result]: {'x' * 500}",
    ]
    assert not any(isinstance(message, (ToolMessage, FunctionMessage)) for message in flat)
