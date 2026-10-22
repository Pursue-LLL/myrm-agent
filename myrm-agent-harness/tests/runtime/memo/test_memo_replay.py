"""The decisive proof of the model-call memo: a replayed turn does not call the model again.

These tests drive the real chat model adapter with a fake client, so they exercise the code
path that decides whether the model is paid for. Without a memo scope the adapter must behave
exactly as before; with one, the second call of the same turn must be answered from the
ledger.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from myrm_agent_harness.runtime.memo import LlmCallScope, MemoLedger, llm_call_scope
from myrm_agent_harness.toolkits.llms.adapters.chat_model.model import ChatLiteLLM

RESPONSE: dict[str, Any] = {
    "id": "chatcmpl-memo",
    "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}


class CountingClient:
    """A client that counts how often the model was actually called."""

    def __init__(self) -> None:
        self.calls = 0

    async def acreate(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return dict(RESPONSE)


def _model() -> tuple[ChatLiteLLM, CountingClient]:
    model = ChatLiteLLM(model="gpt-4o-mini", api_key="test-key")
    client = CountingClient()
    model.client = client  # type: ignore[assignment]
    return model, client


def _scope(ledger: MemoLedger, turn_id: str = "turn-1") -> LlmCallScope:
    return LlmCallScope(session_id="session-1", turn_id=turn_id, ledger=ledger)


async def test_without_a_scope_the_model_is_called_every_time() -> None:
    """The feature is inert until a caller opts in."""
    model, client = _model()
    await model.ainvoke("hello")
    await model.ainvoke("hello")
    assert client.calls == 2


async def test_a_repeated_call_of_the_same_turn_is_answered_from_the_ledger() -> None:
    """The interrupted turn, replayed, must not pay for the model twice."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = MemoLedger(Path(tmpdir) / "memo.sqlite3")
        model, client = _model()

        with llm_call_scope(_scope(ledger)):
            first = await model.ainvoke("hello")
        assert client.calls == 1
        assert first.content == "hello"

        # The same turn, replayed after a crash: a new scope, the same turn identity.
        with llm_call_scope(_scope(ledger)):
            second = await model.ainvoke("hello")
        assert client.calls == 1, "the model must not be called a second time"
        assert second.content == "hello"


async def test_another_turn_is_not_answered_from_the_ledger() -> None:
    """A different turn is a different question, even with the same wording."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = MemoLedger(Path(tmpdir) / "memo.sqlite3")
        model, client = _model()

        with llm_call_scope(_scope(ledger, "turn-1")):
            await model.ainvoke("hello")
        with llm_call_scope(_scope(ledger, "turn-2")):
            await model.ainvoke("hello")
        assert client.calls == 2


async def test_another_model_is_not_answered_from_the_ledger() -> None:
    """A failover swaps the model; the first model's answer must not answer for it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = MemoLedger(Path(tmpdir) / "memo.sqlite3")
        model, client = _model()

        with llm_call_scope(_scope(ledger)):
            await model.ainvoke("hello")
        # The same turn, but the agent failed over to another model.
        model.model_name = "gpt-4o"
        with llm_call_scope(_scope(ledger)):
            await model.ainvoke("hello")
        assert client.calls == 2


async def test_another_request_is_not_answered_from_the_ledger() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = MemoLedger(Path(tmpdir) / "memo.sqlite3")
        model, client = _model()

        with llm_call_scope(_scope(ledger)):
            await model.ainvoke("hello")
        with llm_call_scope(_scope(ledger)):
            await model.ainvoke("goodbye")
        assert client.calls == 2
