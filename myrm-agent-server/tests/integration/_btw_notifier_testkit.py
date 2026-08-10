"""Shared test infrastructure for btw-notifier integration tests.

Contains the fake channel adapter, dispatcher fakes, review-store seeder,
notifier harness, and event helpers used by ``test_btw_notifier_e2e.py``.
Kept out of the test module so the test file stays focused on the cases.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from myrm_agent_harness.infra.pubsub.event_bus import PubSubBus
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
    VerificationResult,
)

from app.channels.reliability.retry import RetryConfig
from app.channels.types.status import ChannelStatus
from app.core.channel_bridge.btw_notifier import BtwTaskNotifier
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus


def _fake_channel(captured: list[object]) -> MagicMock:
    """Build a fake channel adapter that records sent messages."""
    ch = MagicMock()
    ch.status = ChannelStatus.RUNNING
    ch.retry_config = RetryConfig(max_retries=1, base_delay=0.01, max_delay=0.01, jitter=0)
    ch.should_retry = lambda _exc: False
    ch.extract_retry_after = lambda _exc: None
    ch.activity = MagicMock()

    async def _send(msg: object) -> None:
        captured.append(msg)

    ch.send = _send
    return ch


class _PassVerifier:
    """Verifier that always accepts the produced result."""

    async def verify(self, task: KanbanTask, result: str) -> VerificationResult:
        return VerificationResult(passed=True, reason="ok")


class _FakeRunner:
    """Minimal TaskRunner that records calls and succeeds immediately."""

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        return (True, "work done")


def _btw_task(
    task_id: str,
    title: str,
    result: str,
    *,
    channel: str,
    chat_id: str,
    thread_id: str = "",
    user_id: str = "",
) -> MagicMock:
    """Build a /btw kanban task stub with the channel routing metadata."""
    task = MagicMock()
    task.task_id = task_id
    task.title = title
    task.result = result
    task.error = ""
    task.metadata = {
        "background_source": "btw",
        "channel": channel,
        "chat_id": chat_id,
        "thread_id": thread_id,
        "user_id": user_id,
        "locale": "en",
    }
    return task


async def _make_review_store(task_id: str, metadata: dict[str, object]) -> tuple[InMemoryKanbanStore, KanbanBoard]:
    """Seed a store with one IN_REVIEW task under a test board."""
    store = InMemoryKanbanStore()
    board = KanbanBoard(
        board_id="b1",
        name="Test",
        settings=BoardSettings(
            max_concurrent_tasks=3,
            heartbeat_interval_seconds=10,
            zombie_timeout_seconds=120,
        ),
    )
    await store.save_board(board)
    task = KanbanTask(
        task_id=task_id,
        board_id="b1",
        title=f"Task {task_id}",
        status=TaskStatus.IN_REVIEW,
        priority=TaskPriority.NORMAL,
        require_approval=True,
        result="draft result",
        metadata=metadata,
    )
    await store.save_task(task)
    return store, board


async def _make_notifier_harness(
    captured: list[object],
) -> tuple[ServerEventBus, BtwTaskNotifier, MagicMock]:
    """Build a running BtwTaskNotifier whose channel lookups all hit one fake channel.

    Returns the bus, the running notifier, and the patched gateway so tests can
    publish events and assert on the captured OutboundMessages.
    """
    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()
    fake_ch = _fake_channel(captured)
    mock_gateway = MagicMock()
    mock_gateway.bus.channels.get.return_value = fake_ch
    return bus, notifier, mock_gateway


def _background_event(
    bus: ServerEventBus,
    *,
    task_id: str,
    status: str,
    title: str,
    result: str,
    channel: str = "test-ch",
    chat_id: str = "chat-0",
    thread_id: str = "",
    user_id: str = "",
    locale: str = "en",
) -> None:
    """Publish a BACKGROUND_TASK_DONE event on the bus."""
    bus.publish(
        AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": task_id,
                "status": status,
                "title": title,
                "result": result,
                "channel": channel,
                "chat_id": chat_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "locale": locale,
            },
        )
    )


@contextmanager
def _patched_delivery(mock_gateway: MagicMock) -> Iterator[None]:
    """Route BtwTaskNotifier channel lookups and component downgrades to the fake gateway."""
    with (
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
    ):
        yield


async def _wait_for_messages(captured: list[object], count: int, timeout: float = 2.0) -> None:
    """Poll until ``count`` OutboundMessages arrive on the fake channel."""
    deadline = asyncio.get_running_loop().time() + timeout
    while len(captured) < count:
        if asyncio.get_running_loop().time() >= deadline:
            return
        await asyncio.sleep(0.02)
