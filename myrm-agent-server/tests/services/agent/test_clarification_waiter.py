"""PhaseWaiter unit tests — in-process suspend/resume for Deep Research phases."""

import asyncio

import pytest

from app.services.agent.streaming import (
    PHASE_TIMEOUT_SECONDS,
    PhaseWaiter,
    _phase_waiters,
)


@pytest.fixture(autouse=True)
def _cleanup_waiters():
    """Ensure global waiter registry is empty between tests."""
    _phase_waiters.clear()
    yield
    _phase_waiters.clear()


class TestPhaseWaiter:
    def test_register_and_get(self):
        waiter = PhaseWaiter.register("msg-1")
        assert PhaseWaiter.get("msg-1") is waiter
        assert PhaseWaiter.get("msg-999") is None

    def test_is_resolved_before_resolve(self):
        waiter = PhaseWaiter.register("msg-2")
        assert waiter.is_resolved is False

    def test_resolve_sets_answer(self):
        waiter = PhaseWaiter.register("msg-3")
        waiter.resolve("user answer")
        assert waiter.is_resolved is True

    @pytest.mark.asyncio
    async def test_wait_returns_answer(self):
        waiter = PhaseWaiter.register("msg-4")

        async def _delayed_resolve():
            await asyncio.sleep(0.05)
            waiter.resolve("hello")

        asyncio.create_task(_delayed_resolve())
        result = await waiter.wait_for_answer()
        assert result == "hello"
        assert PhaseWaiter.get("msg-4") is None

    @pytest.mark.asyncio
    async def test_wait_empty_answer_for_skip(self):
        waiter = PhaseWaiter.register("msg-5")

        async def _delayed_resolve():
            await asyncio.sleep(0.05)
            waiter.resolve("")

        asyncio.create_task(_delayed_resolve())
        result = await waiter.wait_for_answer()
        assert result == ""

    @pytest.mark.asyncio
    async def test_wait_returns_structured_answer(self):
        waiter = PhaseWaiter.register("msg-structured")

        async def _delayed_resolve():
            await asyncio.sleep(0.05)
            waiter.resolve({"question_1": "alpha", "question_2": ["beta", "gamma"]})

        asyncio.create_task(_delayed_resolve())
        result = await waiter.wait_for_answer()
        assert result == {"question_1": "alpha", "question_2": ["beta", "gamma"]}

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, monkeypatch):
        monkeypatch.setattr("app.services.agent.streaming.PHASE_TIMEOUT_SECONDS", 0.1)
        waiter = PhaseWaiter.register("msg-6")
        result = await waiter.wait_for_answer()
        assert result is None
        assert PhaseWaiter.get("msg-6") is None

    @pytest.mark.asyncio
    async def test_cleanup_on_wait_complete(self):
        waiter = PhaseWaiter.register("msg-7")
        assert "msg-7" in _phase_waiters

        waiter.resolve("done")
        await waiter.wait_for_answer()
        assert "msg-7" not in _phase_waiters

    def test_timeout_constant(self):
        assert PHASE_TIMEOUT_SECONDS == 300

    def test_plan_key_namespace_isolation(self):
        """Plan and clarify waiters use different key namespaces."""
        clarify_waiter = PhaseWaiter.register("msg-iso")
        plan_waiter = PhaseWaiter.register("plan:msg-iso")
        assert PhaseWaiter.get("msg-iso") is clarify_waiter
        assert PhaseWaiter.get("plan:msg-iso") is plan_waiter
        assert clarify_waiter is not plan_waiter
