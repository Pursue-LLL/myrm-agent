"""MediaFilterProcessor leaves a turn's media alone while the turn's signed reasoning blocks are in flight.

A signed block is bound to every message before it, so retiring an earlier screenshot while a block written after it
is still to be replayed would make the provider refuse that block. The window therefore waits for the turn to end,
unless a request would carry more media than a provider takes.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.media_filter import MediaFilterProcessor
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY
from myrm_agent_harness.toolkits.llms.capability_learner import ModelCapabilityLearner
from myrm_agent_harness.utils.image_utils import is_media_content_item

_BLOCKS = [{"type": "thinking", "thinking": "plan", "signature": "sig"}]
_IMAGE = {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}}
_MOST_MEDIA_A_REQUEST_MAY_CARRY = 20


@pytest.fixture(autouse=True)
def _reset_learner() -> None:
    ModelCapabilityLearner._instance = None


def _call(number: int, *, signed: bool) -> AIMessage:
    kwargs = {THINKING_BLOCKS_KEY: _BLOCKS} if signed else {}
    call = {"name": "screenshot", "args": {}, "id": f"c{number}", "type": "tool_call"}
    return AIMessage(content="", tool_calls=[call], additional_kwargs=kwargs)


def _shot(number: int) -> ToolMessage:
    return ToolMessage(content=[{"type": "text", "text": f"shot {number}"}, dict(_IMAGE)], tool_call_id=f"c{number}")


def _turn(first: int, last: int, *, signed: bool) -> list[BaseMessage]:
    """The tool rounds ``first`` to ``last`` of one turn: a call that lead with a block, then its screenshot."""
    return [message for number in range(first, last + 1) for message in (_call(number, signed=signed), _shot(number))]


async def _filter(messages: list[BaseMessage], *, supports_vision: bool = True) -> list[bool]:
    """Run the filter over ``messages`` (in place, as the pipeline does) and say which still hold media."""
    context = ProcessorContext(
        messages=messages,
        user_query="test",
        metadata={"supports_vision": supports_vision, "model_name": "claude-sonnet-5-5"},
    )
    await MediaFilterProcessor().process(context)
    return _holding_media(messages)


def _holding_media(messages: Sequence[BaseMessage]) -> list[bool]:
    return [any(is_media_content_item(item) for item in m.content) for m in messages if isinstance(m.content, list)]


async def test_a_turn_in_flight_keeps_every_screenshot_it_took() -> None:
    messages = [HumanMessage(content="go"), *_turn(1, 3, signed=True)]

    assert await _filter(messages) == [True, True, True]


async def test_the_users_own_image_stays_while_the_turn_is_in_flight() -> None:
    attached = HumanMessage(content=[{"type": "text", "text": "what is this?"}, dict(_IMAGE)])

    assert await _filter([attached, *_turn(1, 3, signed=True)]) == [True, True, True, True]


async def test_without_signed_blocks_the_window_keeps_the_newest_two() -> None:
    messages = [HumanMessage(content="go"), *_turn(1, 3, signed=False)]

    assert await _filter(messages) == [False, True, True]


async def test_the_next_turn_retires_all_but_the_newest_two_and_keeps_them_retired() -> None:
    ended = [HumanMessage(content="go"), *_turn(1, 3, signed=True), AIMessage(content="done")]
    messages = [*ended, HumanMessage(content="more")]
    assert await _filter(messages) == [False, True, True]

    messages += _turn(4, 5, signed=True)

    assert await _filter(messages) == [False, True, True, True, True]


async def test_past_the_count_a_provider_takes_the_window_applies_again() -> None:
    held = _MOST_MEDIA_A_REQUEST_MAY_CARRY
    messages = [HumanMessage(content="go"), *_turn(1, held, signed=True)]
    assert await _filter(messages) == [True] * held

    messages += _turn(held + 1, held + 1, signed=True)

    assert await _filter(messages) == [False] * (held - 1) + [True, True]


async def test_a_model_that_takes_no_media_loses_all_of_it_at_once() -> None:
    messages = [HumanMessage(content="go"), *_turn(1, 3, signed=True)]

    assert await _filter(messages, supports_vision=False) == [False, False, False]
