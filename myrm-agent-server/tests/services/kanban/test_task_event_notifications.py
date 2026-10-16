"""What the toast, the system notification and the outbound channels are told when a real dispatcher blocks or fails a task.

[INPUT]
- myrm_agent_harness KanbanDispatcher + InMemoryKanbanStore (the real run, block and retry pipeline)
- app.services.kanban.dispatcher_lifecycle::start_dispatcher (POS: the production wiring of the dispatcher's event callbacks)
- app.services.kanban.move_orchestrator::move_task (POS: the manual or agent-initiated move into a column)
- app.services.kanban.event_publisher (POS: the SSE payload every user-facing consumer reads)
- app.core.notifications.dispatcher::_format_message (POS: the text an outbound channel receives)

[OUTPUT]
Pins three tasks that carry the result of an earlier attempt: one the runner blocks for the user, one that fails for
good, and one that hits a provider rate limit and is retried on its own. The first two report their own reason, not the
old result; the retry produces no message at all, because it resumes by itself. The same holds for a card moved into a
blocked column, by a user or by an agent that waits until a given time.

[POS]
tests/services/kanban/test_task_event_notifications.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskExecutionResult,
    TaskStatus,
)

from app.core.notifications.dispatcher import _format_message
from app.services.event.app_event_bus import AppEvent, AppEventType
from app.services.kanban import event_publisher
from app.services.kanban.dispatcher_lifecycle import shutdown_dispatchers, start_dispatcher
from app.services.kanban.move_orchestrator import move_task

BOARD_ID = "b1"
STALE_RESULT = "Draft summary written by the first attempt"
DECISION_REASON = "Need your decision: use Postgres or SQLite for the report store?"
CRASH_ERROR = "Worker crashed: disk full"
WAIT_SECONDS = 20

BLOCKED_BY_USER = "human001"
FAILED_FOR_GOOD = "failed01"
RETRIED_ON_ITS_OWN = "retry001"

# task id -> (what the runner reports, retries the task is allowed)
SCENARIOS: dict[str, tuple[tuple[bool, str] | TaskExecutionResult, int]] = {
    BLOCKED_BY_USER: (TaskExecutionResult.blocked(DECISION_REASON, block_kind=BlockKind.HUMAN), 3),
    FAILED_FOR_GOOD: ((False, CRASH_ERROR), 0),
    RETRIED_ON_ITS_OWN: ((False, "429 Too Many Requests"), 3),
}


class _Runner:
    async def run(self, task: KanbanTask) -> tuple[bool, str] | TaskExecutionResult:
        return SCENARIOS[task.task_id][0]


async def _published_outcomes() -> dict[str, dict[str, str]]:
    """Run the three tasks through a real dispatcher and return the last blocked/failed payload published per task."""
    store = InMemoryKanbanStore()
    await store.save_board(
        KanbanBoard(
            board_id=BOARD_ID,
            name="Board",
            settings=BoardSettings(max_concurrent_tasks=4, heartbeat_interval_seconds=1, zombie_timeout_seconds=60),
        )
    )
    for task_id, (_, max_retries) in SCENARIOS.items():
        await store.save_task(
            KanbanTask(
                task_id=task_id,
                board_id=BOARD_ID,
                title=f"Task {task_id}",
                status=TaskStatus.READY,
                result=STALE_RESULT,
                max_retries=max_retries,
            )
        )

    dispatchers: dict[str, KanbanDispatcher] = {}
    outcomes: dict[str, dict[str, str]] = {}

    def capture(event: AppEvent) -> None:
        data = event.data
        if event.event_type == AppEventType.KANBAN_TASK_UPDATED and data["action"] in ("task_blocked", "task_failed"):
            outcomes[data["task_id"]] = data

    with patch.object(event_publisher, "get_event_bus") as get_bus:
        get_bus.return_value.publish.side_effect = capture
        await start_dispatcher(store, dispatchers, BOARD_ID, _Runner())  # type: ignore[arg-type]
        try:
            await asyncio.wait_for(_until_all_reported(outcomes), timeout=WAIT_SECONDS)
        finally:
            await shutdown_dispatchers(dispatchers)
    return outcomes


async def _until_all_reported(outcomes: dict[str, dict[str, str]]) -> None:
    while len(outcomes) < len(SCENARIOS):
        await asyncio.sleep(0.02)


@pytest.fixture(scope="module")
def outcomes() -> dict[str, dict[str, str]]:
    return asyncio.run(_published_outcomes())


def _channel_text(data: dict[str, str]) -> str | None:
    return _format_message(AppEvent(event_type=AppEventType.KANBAN_TASK_UPDATED, data=data))


def test_a_task_blocked_for_the_user_reports_the_question_not_the_old_result(outcomes: dict[str, dict[str, str]]) -> None:
    data = outcomes[BLOCKED_BY_USER]
    assert data["detail"] == DECISION_REASON
    assert data["block_kind"] == "human"

    text = _channel_text(data)
    assert text is not None
    assert DECISION_REASON in text
    assert STALE_RESULT not in text


def test_a_task_that_failed_for_good_reports_the_error_not_the_old_result(outcomes: dict[str, dict[str, str]]) -> None:
    data = outcomes[FAILED_FOR_GOOD]
    assert data["action"] == "task_failed"
    assert CRASH_ERROR in data["detail"]
    assert STALE_RESULT not in data["detail"]

    text = _channel_text(data)
    assert text is not None
    assert CRASH_ERROR in text


def test_a_task_retried_on_its_own_after_a_rate_limit_sends_no_message(outcomes: dict[str, dict[str, str]]) -> None:
    data = outcomes[RETRIED_ON_ITS_OWN]
    assert data["action"] == "task_blocked"
    assert data["block_kind"] == "scheduled"
    assert "detail" not in data
    assert _channel_text(data) is None


async def _moved_to_blocked(
    block_kind: BlockKind, blocked_reason: str, scheduled_until: datetime | None = None
) -> dict[str, str]:
    store = InMemoryKanbanStore()
    await store.save_board(KanbanBoard(board_id=BOARD_ID, name="Board"))
    await store.save_task(
        KanbanTask(task_id="moved001", board_id=BOARD_ID, title="Moved task", status=TaskStatus.READY, result=STALE_RESULT)
    )
    with patch.object(event_publisher, "get_event_bus") as get_bus:
        await move_task(
            store,
            {},
            None,
            "moved001",
            TaskStatus.BLOCKED,
            block_kind=block_kind,
            blocked_reason=blocked_reason,
            scheduled_until=scheduled_until,
            wake_dispatcher=lambda _board_id: None,
        )
    return get_bus.return_value.publish.call_args_list[-1].args[0].data


@pytest.mark.asyncio
async def test_a_card_moved_to_a_block_that_waits_for_the_user_reports_the_reason_not_the_old_result() -> None:
    data = await _moved_to_blocked(BlockKind.HUMAN, DECISION_REASON)
    assert data["action"] == "moved"
    assert data["detail"] == DECISION_REASON
    assert data["block_kind"] == "human"

    text = _channel_text(data)
    assert text is not None
    assert DECISION_REASON in text
    assert STALE_RESULT not in text


@pytest.mark.asyncio
async def test_a_card_moved_to_a_block_that_waits_until_a_time_sends_no_message() -> None:
    data = await _moved_to_blocked(BlockKind.SCHEDULED, "Wait for the nightly export", datetime.now(UTC) + timedelta(hours=2))
    assert data["block_kind"] == "scheduled"
    assert _channel_text(data) is None
