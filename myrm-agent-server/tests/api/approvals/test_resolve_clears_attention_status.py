"""Tests that resolving an approval publishes 'idle' session_status to clear sidebar indicator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.approvals.registry import ApprovalRegistry


@pytest.mark.asyncio
async def test_resolve_approval_publishes_idle_status(app, setup_test_database) -> None:
    """POST /{id}/resolve should publish 'idle' session_status for the chat_id."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-1",
        chat_id="chat-resolve-test",
        thread_id="thread-1",
        action_type="shell_execute",
        payload={"cmd": "ls"},
        reason="test",
        severity="warning",
        status="PENDING",
    )

    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer

    with (
        patch(
            "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
            mock_multiplexer_cls,
        ),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=MagicMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                f"/api/v1/approvals/{record.id}/resolve",
                json={"decision": "approve"},
            )

    assert response.status_code == 200
    mock_multiplexer.publish_session_status.assert_called_once_with("chat-resolve-test", "idle", "")


@pytest.mark.asyncio
async def test_resolve_approval_no_publish_when_no_chat_id(app, setup_test_database) -> None:
    """POST /{id}/resolve should NOT publish if record has no chat_id."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-1",
        chat_id=None,
        thread_id="thread-1",
        action_type="shell_execute",
        payload={"cmd": "ls"},
        reason="test",
        severity="warning",
        status="PENDING",
    )

    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer

    with (
        patch(
            "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
            mock_multiplexer_cls,
        ),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=MagicMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                f"/api/v1/approvals/{record.id}/resolve",
                json={"decision": "deny"},
            )

    assert response.status_code == 200
    mock_multiplexer.publish_session_status.assert_not_called()


@pytest.mark.asyncio
async def test_batch_resolve_publishes_idle_for_each_chat_id(app, setup_test_database) -> None:
    """POST /batch-resolve should publish 'idle' for each resolved approval with chat_id."""
    record1 = await ApprovalRegistry.create_approval(
        agent_id="agent-1",
        chat_id="chat-batch-1",
        thread_id="thread-1",
        action_type="shell_execute",
        payload={"cmd": "ls"},
        reason="test",
        severity="warning",
        status="PENDING",
    )
    record2 = await ApprovalRegistry.create_approval(
        agent_id="agent-1",
        chat_id="chat-batch-2",
        thread_id="thread-2",
        action_type="file_write",
        payload={"path": "/tmp/x"},
        reason="test",
        severity="warning",
        status="PENDING",
    )

    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer

    with (
        patch(
            "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
            mock_multiplexer_cls,
        ),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=MagicMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/v1/approvals/batch-resolve",
                json={"approval_ids": [record1.id, record2.id], "decision": "approve"},
            )

    assert response.status_code == 200
    assert mock_multiplexer.publish_session_status.call_count == 2
    calls = mock_multiplexer.publish_session_status.call_args_list
    assert calls[0].args == ("chat-batch-1", "idle", "")
    assert calls[1].args == ("chat-batch-2", "idle", "")
