"""ClarificationWaiter unit tests — in-process suspend/resume for Deep Research."""

import asyncio

import pytest

from app.services.agent.streaming import (
    CLARIFICATION_TIMEOUT_SECONDS,
    ClarificationWaiter,
    _clarification_waiters,
)


@pytest.fixture(autouse=True)
def _cleanup_waiters():
    """Ensure global waiter registry is empty between tests."""
    _clarification_waiters.clear()
    yield
    _clarification_waiters.clear()


class TestClarificationWaiter:
    def test_register_and_get(self):
        waiter = ClarificationWaiter.register("msg-1")
        assert ClarificationWaiter.get("msg-1") is waiter
        assert ClarificationWaiter.get("msg-999") is None

    def test_is_resolved_before_resolve(self):
        waiter = ClarificationWaiter.register("msg-2")
        assert waiter.is_resolved is False

    def test_resolve_sets_answer(self):
        waiter = ClarificationWaiter.register("msg-3")
        waiter.resolve("user answer")
        assert waiter.is_resolved is True

    @pytest.mark.asyncio
    async def test_wait_returns_answer(self):
        waiter = ClarificationWaiter.register("msg-4")

        async def _delayed_resolve():
            await asyncio.sleep(0.05)
            waiter.resolve("hello")

        asyncio.create_task(_delayed_resolve())
        result = await waiter.wait_for_answer()
        assert result == "hello"
        assert ClarificationWaiter.get("msg-4") is None

    @pytest.mark.asyncio
    async def test_wait_empty_answer_for_skip(self):
        waiter = ClarificationWaiter.register("msg-5")

        async def _delayed_resolve():
            await asyncio.sleep(0.05)
            waiter.resolve("")

        asyncio.create_task(_delayed_resolve())
        result = await waiter.wait_for_answer()
        assert result == ""

    @pytest.mark.asyncio
    async def test_wait_returns_structured_answer(self):
        waiter = ClarificationWaiter.register("msg-structured")

        async def _delayed_resolve():
            await asyncio.sleep(0.05)
            waiter.resolve({"question_1": "alpha", "question_2": ["beta", "gamma"]})

        asyncio.create_task(_delayed_resolve())
        result = await waiter.wait_for_answer()
        assert result == {"question_1": "alpha", "question_2": ["beta", "gamma"]}

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, monkeypatch):
        monkeypatch.setattr("app.services.agent.streaming.CLARIFICATION_TIMEOUT_SECONDS", 0.1)
        waiter = ClarificationWaiter.register("msg-6")
        result = await waiter.wait_for_answer()
        assert result is None
        assert ClarificationWaiter.get("msg-6") is None

    @pytest.mark.asyncio
    async def test_cleanup_on_wait_complete(self):
        waiter = ClarificationWaiter.register("msg-7")
        assert "msg-7" in _clarification_waiters

        waiter.resolve("done")
        await waiter.wait_for_answer()
        assert "msg-7" not in _clarification_waiters

    def test_timeout_constant(self):
        assert CLARIFICATION_TIMEOUT_SECONDS == 300
