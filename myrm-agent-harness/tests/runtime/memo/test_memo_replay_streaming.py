"""The model-call memo on the streaming path — the path a deployment actually uses.

`core/config/llm.py` defaults `streaming` to True, so the streaming adapter is the one that
has to avoid paying for the model twice. These tests drive it with a fake streaming client.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from myrm_agent_harness.runtime.memo import LlmCallScope, MemoLedger, llm_call_scope
from myrm_agent_harness.toolkits.llms.adapters.chat_model.model import ChatLiteLLM

CHUNKS: list[dict[str, Any]] = [
    {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": "hello"}, "finish_reason": None}],
    },
    {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    },
]


class CountingStreamingClient:
    """A streaming client that counts how often the model was actually called."""

    def __init__(self) -> None:
        self.calls = 0

    async def acreate(self, **kwargs: Any) -> Any:
        self.calls += 1

        async def _stream() -> Any:
            for chunk in CHUNKS:
                yield chunk

        return _stream()


def _model() -> tuple[ChatLiteLLM, CountingStreamingClient]:
    model = ChatLiteLLM(model="gpt-4o-mini", api_key="test-key")
    model.streaming = True
    client = CountingStreamingClient()
    model.client = client  # type: ignore[assignment]
    return model, client


def _scope(ledger: MemoLedger, turn_id: str = "turn-1") -> LlmCallScope:
    return LlmCallScope(session_id="session-1", turn_id=turn_id, ledger=ledger)


async def _drain(model: ChatLiteLLM) -> str:
    parts: list[str] = []
    async for chunk in model.astream("hello"):
        parts.append(str(chunk.content or ""))
    return "".join(parts)


async def test_without_a_scope_the_streaming_model_is_called_every_time() -> None:
    model, client = _model()
    await _drain(model)
    await _drain(model)
    assert client.calls == 2


async def test_a_repeated_streaming_call_of_the_same_turn_is_replayed() -> None:
    """The interrupted turn, replayed, must not pay for the model twice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = MemoLedger(Path(tmpdir) / "memo.sqlite3")
        model, client = _model()

        with llm_call_scope(_scope(ledger)):
            first = await _drain(model)
        assert client.calls == 1
        assert first == "hello"

        with llm_call_scope(_scope(ledger)):
            second = await _drain(model)
        assert client.calls == 1, "the model must not be called a second time"
        assert second == "hello", "the recorded answer must be replayed verbatim"


async def test_another_streaming_turn_is_not_answered_from_the_ledger() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = MemoLedger(Path(tmpdir) / "memo.sqlite3")
        model, client = _model()

        with llm_call_scope(_scope(ledger, "turn-1")):
            await _drain(model)
        with llm_call_scope(_scope(ledger, "turn-2")):
            await _drain(model)
        assert client.calls == 2
