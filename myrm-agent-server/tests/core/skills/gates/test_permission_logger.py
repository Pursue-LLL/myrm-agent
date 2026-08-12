"""Unit tests for the skill permission usage logger.

Covers queue enqueue behavior, lifecycle (start/stop/idempotence), harness
callback registration, and the async DB flush path.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from queue import Queue
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.skills.gates import permission_logger as pl
from app.database.models import SkillPermissionUsageLog


@pytest.fixture(autouse=True)
def _reset_logger_state() -> None:
    pl._log_queue = None
    pl._log_worker_thread = None
    pl._shutdown_flag = False
    yield
    pl._log_queue = None
    pl._log_worker_thread = None
    pl._shutdown_flag = False


def test_callback_enqueues_item_when_queue_ready() -> None:
    """Queued items must carry all permission log fields."""
    queue: Queue[pl._PermissionLogItem] = Queue()
    pl._log_queue = queue

    pl.permission_usage_callback("user-1", "skill-1", "execute", "run", True, "")

    assert queue.qsize() == 1
    item = queue.get_nowait()
    assert item["user_id"] == "user-1"
    assert item["skill_id"] == "skill-1"
    assert item["permission"] == "execute"
    assert item["operation"] == "run"
    assert item["allowed"] is True


def test_callback_skips_when_queue_uninitialized() -> None:
    """Callback must not raise when the logger was never started."""
    pl._log_queue = None
    pl.permission_usage_callback("user-1", "skill-1", "execute", "run", True, "")


def test_start_permission_logger_creates_queue_and_registers_callback() -> None:
    """Start must build the queue and register the harness callback."""
    with (
        patch.object(pl, "Thread", MagicMock()),
        patch(
            "myrm_agent_harness.backends.skills.set_permission_usage_callback"
        ) as mock_set,
    ):
        pl.start_permission_logger()

    assert pl._log_queue is not None
    mock_set.assert_called_once()


def test_start_is_idempotent() -> None:
    """Starting twice must not replace the existing queue or spawn another thread."""
    with (
        patch.object(pl, "Thread", MagicMock()),
        patch("myrm_agent_harness.backends.skills.set_permission_usage_callback"),
    ):
        pl.start_permission_logger()
        queue_ref = pl._log_queue
        pl.start_permission_logger()

    assert pl._log_queue is queue_ref


def test_stop_permission_logger_clears_state() -> None:
    """Stop must clear the queue reference."""
    pl._log_queue = Queue()
    pl.stop_permission_logger()
    assert pl._log_queue is None


@pytest.mark.asyncio
async def test_async_flush_batch_writes_and_commits() -> None:
    """Each batch item must be persisted as SkillPermissionUsageLog and committed."""
    batch: list[pl._PermissionLogItem] = [
        {
            "user_id": "user-1",
            "skill_id": "skill-1",
            "permission": "execute",
            "operation": "run",
            "allowed": True,
            "deny_reason": "",
        },
        {
            "user_id": "user-2",
            "skill_id": "skill-2",
            "permission": "read",
            "operation": "view",
            "allowed": False,
            "deny_reason": "blocked by policy",
        },
    ]
    session = AsyncMock()
    session.add = MagicMock()

    @asynccontextmanager
    async def mock_session_ctx():
        yield session

    with patch("app.core.skills.gates.permission_logger.get_session", mock_session_ctx):
        await pl._async_flush_batch(batch)

    assert session.add.call_count == 2
    session.commit.assert_awaited_once()
    first = session.add.call_args_list[0][0][0]
    assert isinstance(first, SkillPermissionUsageLog)
    assert first.user_id == "user-1"
    assert first.allowed is True
    second = session.add.call_args_list[1][0][0]
    assert second.deny_reason == "blocked by policy"
