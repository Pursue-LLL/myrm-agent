"""Runtime context injection for OpenAI-compatible chat completions streams."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.openai_compat.types import ChatCompletionRequest
from app.services.agent.execution_cache.types import ExecutionMode

_EXPECTED_CTX = {
    "execution_mode": ExecutionMode.POOLED,
    "disabled_skill_roots": ["skills/prebuilt/off"],
}


def _request(*, stream: bool) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        stream=stream,
        chat_id="safe-test-1",
    )


def _capture_stream(calls: list[dict[str, object]]) -> object:
    async def _stream(params, **kwargs):
        calls.append({"params": params, **kwargs})
        yield {"type": "message", "data": "hi"}
        yield {"type": "message_end", "usage": {}}

    return _stream


@pytest.mark.asyncio
async def test_stream_response_injects_runtime_context() -> None:
    from app.api.openai_compat import completions

    calls: list[dict[str, object]] = []
    params = MagicMock()

    with (
        patch.object(completions, "_build_agent_params", AsyncMock(return_value=params)),
        patch(
            "app.services.agent.runtime_context.build_agent_runtime_context",
            AsyncMock(return_value=dict(_EXPECTED_CTX)),
        ),
        patch(
            "app.services.agent.runtime_context.resolve_stream_execution_mode",
            return_value=ExecutionMode.POOLED,
        ),
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            _capture_stream(calls),
        ),
    ):
        chunks = []
        async for chunk in completions._stream_response(_request(stream=True)):
            chunks.append(chunk)

    assert chunks
    assert calls
    assert calls[0]["extra_context"] == _EXPECTED_CTX


@pytest.mark.asyncio
async def test_chat_completions_non_stream_injects_runtime_context() -> None:
    from app.api.openai_compat import completions

    calls: list[dict[str, object]] = []
    params = MagicMock()

    with (
        patch.object(completions, "_build_agent_params", AsyncMock(return_value=params)),
        patch(
            "app.services.agent.runtime_context.build_agent_runtime_context",
            AsyncMock(return_value=dict(_EXPECTED_CTX)),
        ),
        patch(
            "app.services.agent.runtime_context.resolve_stream_execution_mode",
            return_value=ExecutionMode.POOLED,
        ),
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            _capture_stream(calls),
        ),
    ):
        resp = await completions.chat_completions(_request(stream=False), _key_prefix="test-key")

    assert resp.model == "gpt-4o"
    assert calls
    assert calls[0]["extra_context"] == _EXPECTED_CTX
