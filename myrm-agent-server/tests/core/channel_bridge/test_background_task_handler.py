"""Tests for ChannelBackgroundTaskHandler — unit tests for background task lifecycle.

Tests cover spawn, cancel, list, steer, timeout, concurrent limits,
memory cleanup, and event emission without hitting real agent execution.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.background_task import BackgroundTaskInfo
from app.channels.types import InboundMessage, OutboundMessage


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


@pytest.fixture
def handler():
    """Create a fresh ChannelBackgroundTaskHandler."""
    from app.core.channel_bridge.background_task_handler import ChannelBackgroundTaskHandler

    return ChannelBackgroundTaskHandler()


class TestSpawnBackground:
    """Tests for spawn_background."""

    @pytest.mark.asyncio
    async def test_spawn_returns_task_id(self, handler) -> None:
        msg = _make_msg()

        with patch(
            "app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._execute_with_timeout",
            new_callable=AsyncMock,
            return_value="result",
        ):
            task_id = await handler.spawn_background(msg, "test task")

        assert task_id.startswith("bg_")
        assert len(task_id) == 11  # "bg_" + 8 hex chars

    @pytest.mark.asyncio
    async def test_spawn_registers_task(self, handler) -> None:
        msg = _make_msg()

        with patch(
            "app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._execute_with_timeout",
            new_callable=AsyncMock,
            return_value="result",
        ):
            task_id = await handler.spawn_background(msg, "test task")

        assert task_id in handler._tasks
        record = handler._tasks[task_id]
        assert record.prompt == "test task"
        assert record.channel == "test"
        assert record.user_id == "uid1"

    @pytest.mark.asyncio
    async def test_spawn_concurrent_limit(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import MAX_CONCURRENT_TASKS

        msg = _make_msg()

        # Simulate MAX_CONCURRENT_TASKS running tasks
        for i in range(MAX_CONCURRENT_TASKS):
            from app.core.channel_bridge.background_task_handler import _RunningTask

            handler._tasks[f"bg_fake{i:03d}"] = _RunningTask(
                task_id=f"bg_fake{i:03d}",
                prompt=f"task {i}",
                channel="test",
                chat_id="chat1",
                user_id="uid1",
                thread_id=None,
                status="running",
            )

        with pytest.raises(RuntimeError, match="Maximum concurrent"):
            await handler.spawn_background(msg, "one too many")

    @pytest.mark.asyncio
    async def test_spawn_calls_cleanup(self, handler) -> None:
        msg = _make_msg()

        with (
            patch(
                "app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._execute_with_timeout",
                new_callable=AsyncMock,
                return_value="result",
            ),
            patch.object(handler, "cleanup_expired", wraps=handler.cleanup_expired) as mock_cleanup,
        ):
            await handler.spawn_background(msg, "task")

        mock_cleanup.assert_called_once()


class TestCancelBackground:
    """Tests for cancel_background."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(self, handler) -> None:
        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

        from app.core.channel_bridge.background_task_handler import _RunningTask

        cancel_token = CancellationToken()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()

        handler._tasks["bg_test001"] = _RunningTask(
            task_id="bg_test001",
            prompt="cancellable",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            asyncio_task=mock_task,
            cancel_token=cancel_token,
            status="running",
        )

        msg = _make_msg()
        result = await handler.cancel_background(msg, "bg_test001")

        assert result is True
        assert handler._tasks["bg_test001"].status == "cancelled"
        assert cancel_token.is_cancelled
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, handler) -> None:
        msg = _make_msg()
        result = await handler.cancel_background(msg, "bg_nonexist")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_already_completed(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_done001"] = _RunningTask(
            task_id="bg_done001",
            prompt="done",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="completed",
            completed_at=time.time(),
        )

        msg = _make_msg()
        result = await handler.cancel_background(msg, "bg_done001")
        assert result is False


class TestListBackground:
    """Tests for list_background."""

    @pytest.mark.asyncio
    async def test_list_empty(self, handler) -> None:
        msg = _make_msg()
        result = await handler.list_background(msg)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_filters_by_user(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_mine001"] = _RunningTask(
            task_id="bg_mine001",
            prompt="my task",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="running",
        )
        handler._tasks["bg_other01"] = _RunningTask(
            task_id="bg_other01",
            prompt="other task",
            channel="test",
            chat_id="other_chat",
            user_id="uid2",
            thread_id=None,
            status="running",
        )

        msg = _make_msg(user_id="uid1", chat_id="chat1")
        result = await handler.list_background(msg)

        assert len(result) == 1
        assert result[0].task_id == "bg_mine001"

    @pytest.mark.asyncio
    async def test_list_returns_correct_info(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_info001"] = _RunningTask(
            task_id="bg_info001",
            prompt="detailed task",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="completed",
            completed_at=2000.0,
            result="Full result text here",
        )

        msg = _make_msg()
        result = await handler.list_background(msg)

        assert len(result) == 1
        info = result[0]
        assert isinstance(info, BackgroundTaskInfo)
        assert info.task_id == "bg_info001"
        assert info.prompt == "detailed task"
        assert info.status == "completed"
        assert info.completed_at == 2000.0
        assert info.result_preview == "Full result text here"


class TestSteerBackground:
    """Tests for steer_background."""

    @pytest.mark.asyncio
    async def test_steer_running_task(self, handler) -> None:
        from myrm_agent_harness.utils.runtime.steering import SteeringToken

        from app.core.channel_bridge.background_task_handler import _RunningTask

        steering_token = SteeringToken()
        handler._tasks["bg_steer01"] = _RunningTask(
            task_id="bg_steer01",
            prompt="steerable",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            steering_token=steering_token,
            status="running",
        )

        msg = _make_msg()
        result = await handler.steer_background(msg, "bg_steer01", "focus on security")

        assert result is True
        assert steering_token.has_pending
        messages = steering_token.activate()
        assert "focus on security" in messages

    @pytest.mark.asyncio
    async def test_steer_nonexistent(self, handler) -> None:
        msg = _make_msg()
        result = await handler.steer_background(msg, "bg_nonexist", "instruction")
        assert result is False

    @pytest.mark.asyncio
    async def test_steer_completed_task(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_done001"] = _RunningTask(
            task_id="bg_done001",
            prompt="done",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="completed",
        )

        msg = _make_msg()
        result = await handler.steer_background(msg, "bg_done001", "too late")
        assert result is False

    @pytest.mark.asyncio
    async def test_steer_no_steering_token(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_nostkn1"] = _RunningTask(
            task_id="bg_nostkn1",
            prompt="no token",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            steering_token=None,
            status="running",
        )

        msg = _make_msg()
        result = await handler.steer_background(msg, "bg_nostkn1", "instruction")
        assert result is False


class TestCleanupExpired:
    """Tests for cleanup_expired."""

    def test_removes_old_completed_tasks(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_old0001"] = _RunningTask(
            task_id="bg_old0001",
            prompt="old",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="completed",
            completed_at=time.time() - 7200,
        )
        handler._tasks["bg_new0001"] = _RunningTask(
            task_id="bg_new0001",
            prompt="new",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="completed",
            completed_at=time.time() - 100,
        )

        removed = handler.cleanup_expired(max_age_seconds=3600.0)

        assert removed == 1
        assert "bg_old0001" not in handler._tasks
        assert "bg_new0001" in handler._tasks

    def test_does_not_remove_running_tasks(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_run0001"] = _RunningTask(
            task_id="bg_run0001",
            prompt="running",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="running",
        )

        removed = handler.cleanup_expired(max_age_seconds=0)
        assert removed == 0
        assert "bg_run0001" in handler._tasks

    def test_empty_tasks_no_error(self, handler) -> None:
        removed = handler.cleanup_expired()
        assert removed == 0


class TestExecuteBackground:
    """Tests for _execute_background (integration with mocks)."""

    @pytest.mark.asyncio
    async def test_execute_collects_full_output(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        record = _RunningTask(
            task_id="bg_exec001",
            prompt="test execution",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
        )
        handler._tasks[record.task_id] = record

        async def mock_execute_stream(*args, **kwargs):
            yield OutboundMessage(
                channel="test",
                recipient_id="chat1",
                content="Part 1",
                user_id="uid1",
            )
            yield OutboundMessage(
                channel="test",
                recipient_id="chat1",
                content="Part 2",
                user_id="uid1",
            )

        with (
            patch("app.core.channel_bridge.agent_executor.ChannelAgentExecutor") as mock_executor_cls,
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._push_result", new_callable=AsyncMock),
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._emit_event"),
        ):
            mock_executor = MagicMock()
            mock_executor.execute_stream = mock_execute_stream
            mock_executor_cls.return_value = mock_executor

            result = await handler._execute_background(record)

        assert "Part 1" in result
        assert "Part 2" in result
        assert record.status == "completed"
        assert record.result is not None

    @pytest.mark.asyncio
    async def test_execute_uses_isolated_chat_id(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        record = _RunningTask(
            task_id="bg_iso0001",
            prompt="isolated",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
        )
        handler._tasks[record.task_id] = record

        captured_msg: list[InboundMessage] = []

        async def mock_execute_stream(msg, *args, **kwargs):
            captured_msg.append(msg)
            return
            yield  # make it an async generator

        with (
            patch("app.core.channel_bridge.agent_executor.ChannelAgentExecutor") as mock_executor_cls,
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._push_result", new_callable=AsyncMock),
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._emit_event"),
        ):
            mock_executor = MagicMock()
            mock_executor.execute_stream = mock_execute_stream
            mock_executor_cls.return_value = mock_executor

            await handler._execute_background(record)

        assert len(captured_msg) == 1
        assert captured_msg[0].chat_id == f"bg_{record.task_id}"

    @pytest.mark.asyncio
    async def test_execute_creates_tokens(self, handler) -> None:
        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
        from myrm_agent_harness.utils.runtime.steering import SteeringToken

        from app.core.channel_bridge.background_task_handler import _RunningTask

        record = _RunningTask(
            task_id="bg_tok0001",
            prompt="token test",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
        )
        handler._tasks[record.task_id] = record

        async def mock_execute_stream(*args, **kwargs):
            return
            yield

        with (
            patch("app.core.channel_bridge.agent_executor.ChannelAgentExecutor") as mock_executor_cls,
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._push_result", new_callable=AsyncMock),
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._emit_event"),
        ):
            mock_executor = MagicMock()
            mock_executor.execute_stream = mock_execute_stream
            mock_executor_cls.return_value = mock_executor

            await handler._execute_background(record)

        assert isinstance(record.cancel_token, CancellationToken)
        assert isinstance(record.steering_token, SteeringToken)

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        record = _RunningTask(
            task_id="bg_err0001",
            prompt="error task",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
        )
        handler._tasks[record.task_id] = record

        async def mock_execute_stream(*args, **kwargs):
            raise ValueError("Test error")
            yield  # noqa: RET503

        with (
            patch("app.core.channel_bridge.agent_executor.ChannelAgentExecutor") as mock_executor_cls,
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._push_error", new_callable=AsyncMock),
            patch("app.core.channel_bridge.background_task_handler.ChannelBackgroundTaskHandler._emit_event"),
        ):
            mock_executor = MagicMock()
            mock_executor.execute_stream = mock_execute_stream
            mock_executor_cls.return_value = mock_executor

            result = await handler._execute_background(record)

        assert record.status == "failed"
        assert "Error" in result
        assert record.completed_at is not None


class TestExecuteWithTimeout:
    """Tests for _execute_with_timeout."""

    @pytest.mark.asyncio
    async def test_timeout_marks_failed(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        record = _RunningTask(
            task_id="bg_tmo0001",
            prompt="slow task",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
        )
        handler._tasks[record.task_id] = record

        async def slow_execute(rec):
            await asyncio.sleep(100)
            return "never"

        with (
            patch.object(handler, "_execute_background", side_effect=slow_execute),
            patch.object(handler, "_push_error", new_callable=AsyncMock),
            patch("app.core.channel_bridge.background_task_handler.TASK_TIMEOUT_SECONDS", 0.05),
        ):
            await handler._execute_with_timeout(record)

        assert record.status == "failed"
        assert "timed out" in (record.result or "").lower()
        assert record.completed_at is not None


class TestOnTaskDone:
    """Tests for _on_task_done callback."""

    def test_marks_running_as_completed(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_done001"] = _RunningTask(
            task_id="bg_done001",
            prompt="task",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="running",
        )

        handler._on_task_done("bg_done001")

        assert handler._tasks["bg_done001"].status == "completed"
        assert handler._tasks["bg_done001"].completed_at is not None

    def test_does_not_change_non_running(self, handler) -> None:
        from app.core.channel_bridge.background_task_handler import _RunningTask

        handler._tasks["bg_canc001"] = _RunningTask(
            task_id="bg_canc001",
            prompt="task",
            channel="test",
            chat_id="chat1",
            user_id="uid1",
            thread_id=None,
            status="cancelled",
            completed_at=1000.0,
        )

        handler._on_task_done("bg_canc001")

        assert handler._tasks["bg_canc001"].status == "cancelled"
        assert handler._tasks["bg_canc001"].completed_at == 1000.0
