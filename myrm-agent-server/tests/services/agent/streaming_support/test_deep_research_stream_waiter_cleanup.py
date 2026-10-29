"""A Deep Research stream closed while it waits for the user leaves no waiter behind.

Real scenario: the research plan is waiting for the user's confirmation and the browser tab is closed. The stream ends,
and the plan and clarify keys must be gone at once; a key left until the phase timeout would answer a later request
for the same message as if the old wait were still open.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent import streaming
from app.services.agent.streaming import PhaseWaiter
from app.services.agent.streaming_support.deep_research_stream import ai_deep_research_service_stream

MESSAGE_ID = "msg-dr-cleanup"


@pytest.fixture(autouse=True)
def _empty_waiter_registry() -> None:
    streaming._phase_waiters.clear()


@pytest.mark.asyncio
async def test_closing_the_stream_while_the_plan_waits_clears_the_waiters() -> None:
    callbacks: dict[str, Callable[..., object]] = {}
    waiting: list[asyncio.Task[object]] = []

    async def run(**_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        # Shielded so that closing the stream does not cancel the wait itself: only the stream's own cleanup may clear it.
        waiting.append(asyncio.ensure_future(callbacks["plan"]("1. compare")))
        await asyncio.shield(waiting[0])
        return
        yield

    def build(**kwargs: Callable[..., object]) -> MagicMock:
        callbacks["plan"] = kwargs["on_plan_ready"]
        orchestrator = MagicMock()
        orchestrator.run = run
        return orchestrator

    with (
        patch("app.services.budget.enforcer.should_block_execution", new_callable=AsyncMock, return_value=False),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch("myrm_agent_harness.agent.deep_research.DeepResearchOrchestrator", side_effect=build),
    ):
        stream = ai_deep_research_service_stream(
            llm=MagicMock(), query="compare frameworks", message_id=MESSAGE_ID, context={"session_id": "session-dr"}
        )
        async for event in stream:
            data = event.get("data")
            if isinstance(data, dict) and data.get("phase") == "plan_confirm" and data.get("status") == "waiting":
                assert PhaseWaiter.get(f"plan:{MESSAGE_ID}") is not None
                break
        await stream.aclose()  # type: ignore[attr-defined]

    assert PhaseWaiter.get(f"plan:{MESSAGE_ID}") is None
    assert PhaseWaiter.get(MESSAGE_ID) is None
    for task in waiting:
        task.cancel()
