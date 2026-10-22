"""The Deep Research clarify phase reports who settled the question, so the card can show it after a reload.

Real scenario: a Deep Research run asks which framework to compare. The user answers, skips, or leaves and the phase
timeout resolves it; each ends in one ``clarify`` / ``resolved`` status event, and its ``answerRecord`` is what the
collector persists on the card.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent import streaming
from app.services.agent.streaming import PhaseWaiter, ai_deep_research_service_stream

MESSAGE_ID = "msg-dr-clarify"
_NO_ANSWER = object()


@pytest.fixture(autouse=True)
def _empty_waiter_registry() -> None:
    streaming._phase_waiters.clear()


async def _resolved_clarify_event(answer: object, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Run the stream until its clarify phase resolves with ``answer`` (``_NO_ANSWER``: nobody answers in time)."""
    on_clarify: dict[str, Callable[..., object]] = {}

    async def run(**_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        asking = asyncio.create_task(on_clarify["ask"](MagicMock()))
        await asyncio.sleep(0)
        if answer is not _NO_ANSWER:
            waiter = PhaseWaiter.get(MESSAGE_ID)
            assert waiter is not None
            waiter.resolve(answer)  # type: ignore[arg-type]
        await asking
        return
        yield

    def build(**kwargs: Callable[..., object]) -> MagicMock:
        on_clarify["ask"] = kwargs["on_clarify"]
        orchestrator = MagicMock()
        orchestrator.run = run
        return orchestrator

    monkeypatch.setattr(streaming, "PHASE_TIMEOUT_SECONDS", 0.05)
    with (
        patch("app.services.budget.enforcer.should_block_execution", new_callable=AsyncMock, return_value=False),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch("myrm_agent_harness.agent.deep_research.DeepResearchOrchestrator", side_effect=build),
    ):
        async for event in ai_deep_research_service_stream(
            llm=MagicMock(),
            query="compare frameworks",
            message_id=MESSAGE_ID,
            context={"session_id": "session-dr-clarify"},
        ):
            data = event.get("data")
            if isinstance(data, dict) and data.get("phase") == "clarify" and data.get("status") == "resolved":
                return data
    raise AssertionError("the clarify phase never resolved")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "expected_record", "expected_skipped"),
    [
        ({"framework": "langchain"}, {"by": "user", "value": {"framework": "langchain"}}, False),
        ("langgraph", {"by": "user", "value": "langgraph"}, False),
        ("", {"by": "user", "value": ""}, True),
        (_NO_ANSWER, {"by": "timeout", "value": {}}, True),
    ],
)
async def test_clarify_resolved_event_names_who_settled_the_question(
    answer: object,
    expected_record: dict[str, object],
    expected_skipped: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = await _resolved_clarify_event(answer, monkeypatch)

    assert data["answerRecord"] == expected_record
    assert data["skipped"] is expected_skipped
