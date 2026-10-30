"""Fixtures of the unit tests of the run a fired approval timer starts."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.services.agent.streaming_support import hitl_timeout
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from app.services.copilot.run_digest_store import RunDigestStore
from tests.support.hitl_timeout_run import CHAT_ID, card_collector


@pytest.fixture(autouse=True)
def _fresh_scheduler() -> Iterator[None]:
    ApprovalTimeoutScheduler.get().cancel_all()
    yield
    ApprovalTimeoutScheduler.get().cancel_all()


@pytest.fixture
def parked() -> Iterator[StreamContentCollector]:
    RunDigestStore.begin_run(CHAT_ID)
    collector = card_collector(CHAT_ID)
    yield collector
    collector.cleanup()
    RunDigestStore.clear(CHAT_ID)


@pytest.fixture
def stops_at_a_card() -> Iterator[list[bool]]:
    """Whether the stand-in agent stream of ``resumed_run`` ends at a card of its own (empty: it finishes)."""
    flag: list[bool] = []
    yield flag


@pytest.fixture
def stored_history() -> AsyncMock:
    """The chat's stored history as the history loader hands it to the timer run (empty unless a test fills it)."""
    return AsyncMock(return_value=[])


@pytest.fixture
def received_params() -> list[object]:
    """The params the stand-in agent stream of ``resumed_run`` was started with."""
    return []


@pytest.fixture
def registered_runs() -> list[StreamContentCollector | None]:
    """The chat's collector as the stand-in agent stream of ``resumed_run`` sees it once its first chunk was collected."""
    return []


@pytest.fixture
def armed_timer() -> MagicMock:
    """Stand-in for the arming of the next interrupt's timer, which ``_resume_after_timeout`` does as its run stops."""
    return MagicMock()


@pytest.fixture
def resumed_run(
    stops_at_a_card: list[bool],
    stored_history: AsyncMock,
    received_params: list[object],
    registered_runs: list[StreamContentCollector | None],
    armed_timer: MagicMock,
) -> Iterator[list[bool]]:
    """A stand-in agent stream for ``_resume_after_timeout``; the list records the parked card as the run starts."""
    seen: list[bool] = []

    async def stream(**kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        received_params.append(kwargs.get("params"))
        collector = ACTIVE_COLLECTORS.get(CHAT_ID)
        seen.append(collector is not None and collector.has_pending_tool_approval())
        yield {"type": "message", "data": "continued"}
        registered_runs.append(ACTIVE_COLLECTORS.get(CHAT_ID))
        if stops_at_a_card:
            yield {
                "type": "tool_approval_request",
                "messageId": "msg-1",
                "data": {"actionRequests": [], "extensions": {"timeout": {"seconds": 45, "behavior": "allow"}}},
            }

    with (
        patch("app.services.agent.streaming.ai_agent_service_stream", new=stream),
        patch("app.services.agent.runtime_context.build_agent_runtime_context", new=AsyncMock(return_value={})),
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new=AsyncMock()),
        patch("app.services.chat.chat_service.ChatService.load_web_chat_history", new=stored_history),
        patch.object(hitl_timeout, "arm_interrupt_timeout", new=armed_timer),
    ):
        yield seen
