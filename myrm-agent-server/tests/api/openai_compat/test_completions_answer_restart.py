"""Non-streaming chat completions honour the stream's restart contract.

The streaming branch forwards each delta as it arrives and cannot retract text already sent (OpenAI SSE has no
retraction), so only the non-streaming branch, which assembles one final answer, applies the restart.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.openai_compat import completions
from app.api.openai_compat.types import ChatCompletionRequest, ChatCompletionResponse, ChatMessage

_Event = dict[str, object]


async def _non_stream_answer(events: Sequence[_Event]) -> str:
    async def _stream(*_args: object, **_kwargs: object) -> AsyncIterator[_Event]:
        for event in events:
            yield event

    request = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="hello")],
        stream=False,
        chat_id="safe-test-1",
    )
    with (
        patch.object(completions, "_build_agent_params", AsyncMock(return_value=MagicMock())),
        patch("app.services.agent.runtime_context.build_agent_runtime_context", AsyncMock(return_value={})),
        patch.object(completions, "ai_agent_service_stream", _stream),
    ):
        response = await completions.chat_completions(request, _key_prefix="test")
    assert isinstance(response, ChatCompletionResponse)
    content = response.choices[0].message.content
    assert content is not None
    return content


@pytest.mark.asyncio
async def test_restart_replaces_the_in_flight_segment_once() -> None:
    answer = await _non_stream_answer(
        [
            {"type": "message", "data": "The price is 1"},
            {"type": "status", "restart": True, "data": {"status": "retrying"}},
            {"type": "message", "data": "The price is 12 USD."},
            {"type": "message_end", "usage": {}},
        ]
    )

    assert answer == "The price is 12 USD."


@pytest.mark.asyncio
async def test_restart_keeps_text_before_the_last_tool_step() -> None:
    answer = await _non_stream_answer(
        [
            {"type": "message", "data": "Checking. "},
            {"type": "tool_start", "data": {"name": "lookup"}},
            {"type": "message", "data": "The price is 1"},
            {"type": "model_escalated", "data": {"restart": True}},
            {"type": "message", "data": "The price is 12 USD."},
            {"type": "message_end", "usage": {}},
        ]
    )

    assert answer == "Checking. The price is 12 USD."


@pytest.mark.asyncio
async def test_every_text_event_shape_is_still_collected() -> None:
    answer = await _non_stream_answer(
        [
            {"type": "message_chunk", "content": "a"},
            {"type": "message", "data": "b"},
            {"type": "message", "data": {"content": "c"}},
            {"type": "message", "data": {"text": "d"}},
            {"type": "message_end", "usage": {}},
        ]
    )

    assert answer == "abcd"
