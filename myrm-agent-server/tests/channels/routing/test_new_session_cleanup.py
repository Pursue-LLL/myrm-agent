"""Tests for /new session boundary cleanup (IR-03).

Validates that ``_handle_new_session`` cancels the running task, flushes
pending messages, resets per-session state, and still marks the peer for
a fresh Chat via the downstream ``handle_new_session`` pure function.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router_commands import RouterCommandsMixin
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage


def _msg(
    content: str = "/new",
    *,
    channel: str = "telegram",
    sender_id: str = "user1",
    chat_id: str | None = None,
    is_group: bool = False,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
    )


def _make_active_task(
    *,
    channel: str = "telegram",
    chat_id: str = "user1",
    placeholder_id: str | None = None,
    done: bool = False,
) -> _ActiveTask:
    task = MagicMock(spec=asyncio.Task)
    task.done.return_value = done
    cancel_token = MagicMock()
    return _ActiveTask(
        task=task,
        cancel_token=cancel_token,
        channel=channel,
        chat_id=chat_id,
        placeholder_id=placeholder_id,
        started_at=0.0,
        requester_id="user1",
    )


@dataclass(slots=True)
class _Host(RouterCommandsMixin):
    _active_tasks: dict[str, _ActiveTask] = field(default_factory=dict)
    _approval_msg_ids: dict[str, str] = field(default_factory=dict)
    _bus: MagicMock = field(default_factory=MagicMock)
    _fx: MagicMock = field(default_factory=MagicMock)
    _gate: MagicMock = field(default_factory=MagicMock)
    _new_session_peers: dict[str, float] = field(default_factory=dict)
    _session_yolo: dict[str, tuple[float, int | None]] = field(default_factory=dict)
    _session_personality: dict[str, str] = field(default_factory=dict)


def _host(**overrides: Any) -> _Host:  # noqa: ANN401
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    fx = MagicMock()
    fx.cleanup_placeholder = AsyncMock()
    gate = MagicMock()
    gate.clear_pending_for_key = MagicMock(return_value=0)
    return _Host(_bus=bus, _fx=fx, _gate=gate, **overrides)


class TestAbortSessionTask:
    """Unit tests for _abort_session_task (shared by /stop and /new)."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_active_task(self) -> None:
        h = _host()
        result = await h._abort_session_task("telegram:user1", reason="test")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancels_token_and_task(self) -> None:
        active = _make_active_task()
        h = _host(_active_tasks={"telegram:user1": active})

        result = await h._abort_session_task("telegram:user1", reason="User /stop command")

        assert result is True
        active.cancel_token.cancel.assert_called_once_with("User /stop command")
        active.task.cancel.assert_called_once()
        assert "telegram:user1" not in h._active_tasks

    @pytest.mark.asyncio
    async def test_skips_task_cancel_if_done(self) -> None:
        active = _make_active_task(done=True)
        h = _host(_active_tasks={"telegram:user1": active})

        await h._abort_session_task("telegram:user1", reason="done")
        active.task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_approval_msg_ids(self) -> None:
        active = _make_active_task()
        h = _host(
            _active_tasks={"telegram:user1": active},
            _approval_msg_ids={"telegram:user1": "msg-42"},
        )
        await h._abort_session_task("telegram:user1", reason="cleanup")
        assert "telegram:user1" not in h._approval_msg_ids

    @pytest.mark.asyncio
    async def test_cleans_up_placeholder(self) -> None:
        active = _make_active_task(placeholder_id="ph-1")
        h = _host(_active_tasks={"telegram:user1": active})

        await h._abort_session_task(
            "telegram:user1",
            reason="test",
            placeholder_text="Stopped.",
        )

        h._fx.cleanup_placeholder.assert_awaited_once_with(
            "telegram", "user1", "ph-1", "Stopped.",
        )

    @pytest.mark.asyncio
    async def test_no_placeholder_cleanup_without_text(self) -> None:
        active = _make_active_task(placeholder_id="ph-1")
        h = _host(_active_tasks={"telegram:user1": active})

        await h._abort_session_task("telegram:user1", reason="silent")
        h._fx.cleanup_placeholder.assert_not_awaited()


class TestHandleNewSession:
    """Integration tests for _handle_new_session (IR-03 /new cleanup)."""

    @pytest.mark.asyncio
    async def test_abort_and_clear_pending_on_active_task(self) -> None:
        active = _make_active_task(placeholder_id="ph-1")
        h = _host(
            _active_tasks={"telegram:user1": active},
            _session_yolo={"telegram:user1": (0.0, None)},
            _session_personality={"telegram:user1": "sassy"},
        )
        h._gate.clear_pending_for_key.return_value = 3

        await h._handle_new_session(_msg())

        active.cancel_token.cancel.assert_called_once()
        h._gate.clear_pending_for_key.assert_called_once_with("telegram:user1")
        assert "telegram:user1" not in h._active_tasks
        assert "telegram:user1" not in h._session_yolo
        assert "telegram:user1" not in h._session_personality
        h._bus.publish_outbound.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_active_task_still_clears_pending(self) -> None:
        h = _host(
            _session_yolo={"telegram:user1": (0.0, None)},
        )
        h._gate.clear_pending_for_key.return_value = 0

        await h._handle_new_session(_msg())

        h._gate.clear_pending_for_key.assert_called_once_with("telegram:user1")
        assert "telegram:user1" not in h._session_yolo
        h._bus.publish_outbound.assert_awaited()

    @pytest.mark.asyncio
    async def test_marks_peer_for_new_session(self) -> None:
        h = _host()

        await h._handle_new_session(_msg())

        assert "telegram:user1" in h._new_session_peers
