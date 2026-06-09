"""Tests for ChannelBackgroundTaskHandler — unit tests for Kanban-backed background task lifecycle.

Tests cover spawn, cancel, list, steer, concurrent limits, and runtime token
management against a mocked KanbanService.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.background_task import BackgroundTaskInfo
from app.channels.types import InboundMessage


def _make_msg(
    channel: str = "test",
    sender_id: str = "user1",
    chat_id: str = "chat1",
    user_id: str = "uid1",
    content: str = "",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content=content,
        user_id=user_id,
    )


def _mock_kanban_task(
    task_id: str = "abc123",
    title: str = "test",
    description: str = "test task",
    status: str = "READY",
    metadata: dict | None = None,
):
    """Create a mock KanbanTask object."""
    from datetime import UTC, datetime

    task = MagicMock()
    task.task_id = task_id
    task.board_id = "board_sys"
    task.title = title
    task.description = description
    task.metadata = metadata or {"background_source": "btw", "user_id": "uid1", "chat_id": "chat1", "channel": "test"}
    task.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    task.completed_at = None
    task.max_runtime_seconds = None

    from myrm_agent_harness.toolkits.kanban.types import TaskStatus

    task.status = getattr(TaskStatus, status, TaskStatus.READY)
    return task


@pytest.fixture
def handler():
    """Create a fresh ChannelBackgroundTaskHandler."""
    from app.core.channel_bridge.background_task_handler import ChannelBackgroundTaskHandler

    h = ChannelBackgroundTaskHandler()
    h._system_board_id = "board_sys"
    return h


@pytest.fixture
def mock_kanban_svc():
    """Mock KanbanService for unit testing."""
    svc = MagicMock()
    svc.store = MagicMock()
    svc.store.list_tasks = AsyncMock(return_value=[])
    svc.store.get_task = AsyncMock(return_value=None)
    svc.store.save_task = AsyncMock()
    svc.store.list_events = AsyncMock(return_value=[])
    svc.list_boards = AsyncMock(return_value=[])
    svc.add_task = AsyncMock()
    svc.move_task = AsyncMock()
    svc.cancel_task_execution = AsyncMock(return_value=True)
    return svc


class TestSpawnBackground:
    """Tests for spawn_background."""

    @pytest.mark.asyncio
    async def test_spawn_returns_task_id(self, handler, mock_kanban_svc) -> None:
        msg = _make_msg()

        mock_task = _mock_kanban_task(task_id="newtask1")
        mock_kanban_svc.add_task = AsyncMock(return_value=mock_task)
        mock_kanban_svc.store.list_tasks = AsyncMock(return_value=[])

        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            with patch.object(handler, "_count_running", new_callable=AsyncMock, return_value=0):
                task_id = await handler.spawn_background(msg, "test task")

        assert task_id == "newtask1"

    @pytest.mark.asyncio
    async def test_spawn_concurrent_limit(self, handler, mock_kanban_svc) -> None:
        from app.core.channel_bridge.background_task_handler import MAX_CONCURRENT_TASKS

        running_tasks = [_mock_kanban_task(task_id=f"run{i}", status="RUNNING") for i in range(MAX_CONCURRENT_TASKS)]
        mock_kanban_svc.store.list_tasks = AsyncMock(return_value=running_tasks)

        msg = _make_msg()

        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            # Also need to make _count_running see proper KanbanService type
            with patch.object(handler, "_count_running", new_callable=AsyncMock, return_value=MAX_CONCURRENT_TASKS):
                with pytest.raises(RuntimeError, match="Maximum concurrent"):
                    await handler.spawn_background(msg, "one too many")

    @pytest.mark.asyncio
    async def test_spawn_sets_metadata(self, handler, mock_kanban_svc) -> None:
        msg = _make_msg(channel="telegram", chat_id="tg_chat", user_id="tg_user")

        mock_task = _mock_kanban_task(task_id="meta001")
        mock_task.metadata = {}
        mock_kanban_svc.add_task = AsyncMock(return_value=mock_task)
        mock_kanban_svc.store.list_tasks = AsyncMock(return_value=[])

        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            with patch.object(handler, "_count_running", new_callable=AsyncMock, return_value=0):
                await handler.spawn_background(msg, "research task")

        assert mock_task.metadata["background_source"] == "btw"
        assert mock_task.metadata["channel"] == "telegram"
        assert mock_task.metadata["chat_id"] == "tg_chat"
        assert mock_task.metadata["user_id"] == "tg_user"
        mock_kanban_svc.store.save_task.assert_called_once_with(mock_task)


class TestCancelBackground:
    """Tests for cancel_background."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(self, handler, mock_kanban_svc) -> None:
        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
        from myrm_agent_harness.utils.runtime.steering import SteeringToken

        cancel_token = CancellationToken()
        handler.register_runtime_tokens("task001", cancel_token, SteeringToken())

        running_task = _mock_kanban_task(task_id="task001", status="RUNNING")
        mock_kanban_svc.store.get_task = AsyncMock(return_value=running_task)

        msg = _make_msg()
        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            result = await handler.cancel_background(msg, "task001")

        assert result is True
        assert cancel_token.is_cancelled
        mock_kanban_svc.move_task.assert_called_once()
        mock_kanban_svc.cancel_task_execution.assert_called_once_with("task001")
        assert "task001" not in handler._runtime_tokens

    @pytest.mark.asyncio
    async def test_cancel_ready_task(self, handler, mock_kanban_svc) -> None:
        ready_task = _mock_kanban_task(task_id="ready01", status="READY")
        mock_kanban_svc.store.get_task = AsyncMock(return_value=ready_task)

        msg = _make_msg()
        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            result = await handler.cancel_background(msg, "ready01")

        assert result is True
        mock_kanban_svc.move_task.assert_called_once()
        mock_kanban_svc.cancel_task_execution.assert_called_once_with("ready01")

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, handler, mock_kanban_svc) -> None:
        mock_kanban_svc.store.get_task = AsyncMock(return_value=None)

        msg = _make_msg()
        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            result = await handler.cancel_background(msg, "nonexist")

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_completed_task(self, handler, mock_kanban_svc) -> None:
        completed_task = _mock_kanban_task(task_id="done001", status="COMPLETED")
        mock_kanban_svc.store.get_task = AsyncMock(return_value=completed_task)

        msg = _make_msg()
        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            result = await handler.cancel_background(msg, "done001")

        assert result is False


class TestListBackground:
    """Tests for list_background."""

    @pytest.mark.asyncio
    async def test_list_empty(self, handler, mock_kanban_svc) -> None:
        mock_kanban_svc.store.list_tasks = AsyncMock(return_value=[])

        msg = _make_msg()
        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            result = await handler.list_background(msg)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_filters_by_user(self, handler, mock_kanban_svc) -> None:
        my_task = _mock_kanban_task(
            task_id="mine001",
            metadata={"background_source": "btw", "user_id": "uid1", "chat_id": "chat1", "channel": "test"},
        )
        other_task = _mock_kanban_task(
            task_id="other01",
            metadata={"background_source": "btw", "user_id": "uid2", "chat_id": "other_chat", "channel": "test"},
        )
        mock_kanban_svc.store.list_tasks = AsyncMock(return_value=[my_task, other_task])

        msg = _make_msg(user_id="uid1", chat_id="chat1")
        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            result = await handler.list_background(msg)

        assert len(result) == 1
        assert result[0].task_id == "mine001"

    @pytest.mark.asyncio
    async def test_list_returns_correct_info(self, handler, mock_kanban_svc) -> None:
        task = _mock_kanban_task(task_id="info001", description="detailed task", status="RUNNING")
        mock_kanban_svc.store.list_tasks = AsyncMock(return_value=[task])

        msg = _make_msg()
        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            result = await handler.list_background(msg)

        assert len(result) == 1
        info = result[0]
        assert isinstance(info, BackgroundTaskInfo)
        assert info.task_id == "info001"
        assert info.prompt == "detailed task"
        assert info.status == "running"


class TestSteerBackground:
    """Tests for steer_background."""

    @pytest.mark.asyncio
    async def test_steer_running_task(self, handler) -> None:
        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
        from myrm_agent_harness.utils.runtime.steering import SteeringToken

        steering_token = SteeringToken()
        handler.register_runtime_tokens("steer01", CancellationToken(), steering_token)

        msg = _make_msg()
        result = await handler.steer_background(msg, "steer01", "focus on security")

        assert result is True
        assert steering_token.has_pending
        messages = steering_token.activate()
        assert "focus on security" in messages

    @pytest.mark.asyncio
    async def test_steer_nonexistent(self, handler) -> None:
        msg = _make_msg()
        result = await handler.steer_background(msg, "nonexist", "instruction")
        assert result is False


class TestRuntimeTokens:
    """Tests for register/unregister runtime tokens."""

    def test_register_and_unregister(self, handler) -> None:
        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
        from myrm_agent_harness.utils.runtime.steering import SteeringToken

        ct = CancellationToken()
        st = SteeringToken()
        handler.register_runtime_tokens("task1", ct, st)

        assert "task1" in handler._runtime_tokens
        assert handler._runtime_tokens["task1"].cancel_token is ct
        assert handler._runtime_tokens["task1"].steering_token is st

        handler.unregister_runtime_tokens("task1")
        assert "task1" not in handler._runtime_tokens

    def test_unregister_nonexistent_no_error(self, handler) -> None:
        handler.unregister_runtime_tokens("nonexist")


class TestEnsureSystemBoard:
    """Tests for _ensure_system_board."""

    @pytest.mark.asyncio
    async def test_creates_board_if_not_exists(self, handler, mock_kanban_svc) -> None:
        handler._system_board_id = None
        mock_kanban_svc.list_boards = AsyncMock(return_value=[])

        mock_board = MagicMock()
        mock_board.board_id = "new_board_123"
        mock_kanban_svc.create_board = AsyncMock(return_value=mock_board)

        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            board_id = await handler._ensure_system_board()

        assert board_id == "new_board_123"
        assert handler._system_board_id == "new_board_123"
        mock_kanban_svc.create_board.assert_called_once()

    @pytest.mark.asyncio
    async def test_reuses_existing_board(self, handler, mock_kanban_svc) -> None:
        handler._system_board_id = None

        existing_board = MagicMock()
        existing_board.board_id = "existing_board"
        existing_board.name = "__background_tasks__"
        mock_kanban_svc.list_boards = AsyncMock(return_value=[existing_board])

        with patch("app.services.kanban.KanbanService") as mock_cls:
            mock_cls.get_instance.return_value = mock_kanban_svc
            board_id = await handler._ensure_system_board()

        assert board_id == "existing_board"
        mock_kanban_svc.create_board.assert_not_called()

    @pytest.mark.asyncio
    async def test_caches_board_id(self, handler) -> None:
        handler._system_board_id = "cached_board"
        board_id = await handler._ensure_system_board()
        assert board_id == "cached_board"
