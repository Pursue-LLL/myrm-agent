"""Regression tests for the memo scope's ContextVar ownership.

The scope token must never outlive the ``__anext__`` call that created it: an async
generator can be closed by a different task (client disconnect, cancel, GC), and
``ContextVar.reset`` rejects a token created in another ``Context``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from myrm_agent_harness.infra.memo.call_scope import LlmCallScope, current_llm_call_scope
from myrm_agent_harness.infra.memo.memo_ledger import MemoLedger

from app.services.agent import memo_scope


def _scope() -> LlmCallScope:
    return LlmCallScope(session_id="session-1", turn_id="turn-1", ledger=MemoLedger(":memory:"))


@pytest.fixture
def scope(monkeypatch: pytest.MonkeyPatch) -> LlmCallScope:
    fake = _scope()
    monkeypatch.setattr(memo_scope, "build_memo_scope", lambda _params: fake)
    return fake


async def _source(expected: LlmCallScope, count: int = 3) -> AsyncIterator[int]:
    for index in range(count):
        assert current_llm_call_scope() is expected
        yield index


async def test_scope_is_active_inside_every_chunk(scope: LlmCallScope) -> None:
    chunks = [chunk async for chunk in memo_scope.memo_scoped_stream(_source(scope), object())]
    assert chunks == [0, 1, 2]


async def test_scope_is_not_leaked_to_the_consumer(scope: LlmCallScope) -> None:
    generator = memo_scope.memo_scoped_stream(_source(scope), object())
    assert await anext(generator) == 0
    assert current_llm_call_scope() is None
    await generator.aclose()


async def test_close_from_another_task_does_not_raise(scope: LlmCallScope) -> None:
    """The exact production failure: advance in one task, aclose in another."""
    generator = memo_scope.memo_scoped_stream(_source(scope), object())
    assert await anext(generator) == 0
    await asyncio.create_task(generator.aclose())


async def test_close_before_first_chunk_does_not_raise(scope: LlmCallScope) -> None:
    generator = memo_scope.memo_scoped_stream(_source(scope), object())
    await asyncio.create_task(generator.aclose())


async def test_without_scope_is_a_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memo_scope, "build_memo_scope", lambda _params: None)

    async def source() -> AsyncIterator[int]:
        yield 1
        yield 2

    assert [chunk async for chunk in memo_scope.memo_scoped_stream(source(), object())] == [1, 2]


async def test_inner_exception_propagates_and_scope_is_restored(scope: LlmCallScope) -> None:
    async def failing() -> AsyncIterator[int]:
        assert current_llm_call_scope() is scope
        raise RuntimeError("boom")
        yield 0  # pragma: no cover

    with pytest.raises(RuntimeError, match="boom"):
        await anext(memo_scope.memo_scoped_stream(failing(), object()))
    assert current_llm_call_scope() is None


class TestBuildMemoScope:
    def _params(self, **overrides: object) -> object:
        from types import SimpleNamespace

        base = {
            "turn_identity": "turn-1",
            "memo_ledger_path": "/tmp/memo-scope-test.db",
            "event_log_session_id": "session-1",
            "chat_id": "chat-1",
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_requires_turn_identity(self) -> None:
        assert memo_scope.build_memo_scope(self._params(turn_identity=None)) is None

    def test_requires_ledger_path(self) -> None:
        assert memo_scope.build_memo_scope(self._params(memo_ledger_path=None)) is None

    def test_requires_session_id(self) -> None:
        assert memo_scope.build_memo_scope(self._params(event_log_session_id=None, chat_id=None)) is None

    def test_ledger_open_failure_degrades_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(_path: str) -> object:
            raise RuntimeError("no ledger")

        monkeypatch.setattr(memo_scope, "MemoLedger", _boom)
        assert memo_scope.build_memo_scope(self._params()) is None

    def test_builds_scope_from_turn_and_event_session(self, tmp_path) -> None:
        params = self._params(memo_ledger_path=str(tmp_path / "memo.db"))
        scope = memo_scope.build_memo_scope(params)
        assert isinstance(scope, LlmCallScope)
        assert (scope.session_id, scope.turn_id) == ("session-1", "turn-1")

    def test_falls_back_to_chat_id(self, tmp_path) -> None:
        params = self._params(
            memo_ledger_path=str(tmp_path / "memo2.db"),
            event_log_session_id=None,
            chat_id="chat-2",
        )
        scope = memo_scope.build_memo_scope(params)
        assert scope is not None
        assert scope.session_id == "chat-2"
