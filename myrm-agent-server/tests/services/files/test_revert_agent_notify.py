"""Unit tests for revert_agent_notify service."""

from __future__ import annotations

from unittest.mock import patch


def test_notify_agent_of_turn_revert_message_scope() -> None:
    from app.services.files.revert_agent_notify import notify_agent_of_turn_revert

    with patch(
        "myrm_agent_harness.agent.file_snapshot.restore_inbox.push_restore_notification",
    ) as mock_push:
        notify_agent_of_turn_revert(
            session_id="chat-1",
            message_id="msg-1",
            reverted_files=["/tmp/a.py"],
        )

    mock_push.assert_called_once_with(
        snapshot_id="turn:msg-1",
        files_restored=1,
        restored_files=["/tmp/a.py"],
    )


def test_notify_agent_of_turn_revert_session_scope() -> None:
    from app.services.files.revert_agent_notify import notify_agent_of_turn_revert

    with patch(
        "myrm_agent_harness.agent.file_snapshot.restore_inbox.push_restore_notification",
    ) as mock_push:
        notify_agent_of_turn_revert(
            session_id="chat-1",
            message_id=None,
            reverted_files=["/tmp/a.py", "/tmp/b.py"],
        )

    mock_push.assert_called_once_with(
        snapshot_id="session:chat-1",
        files_restored=2,
        restored_files=["/tmp/a.py", "/tmp/b.py"],
    )


def test_notify_agent_of_turn_revert_noop_when_empty() -> None:
    from app.services.files.revert_agent_notify import notify_agent_of_turn_revert

    with patch(
        "myrm_agent_harness.agent.file_snapshot.restore_inbox.push_restore_notification",
    ) as mock_push:
        notify_agent_of_turn_revert(
            session_id="chat-1",
            message_id="msg-1",
            reverted_files=[],
        )

    mock_push.assert_not_called()
