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
