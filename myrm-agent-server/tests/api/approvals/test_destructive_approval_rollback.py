"""Unit tests for destructive action approval rollback and allow_always stripping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.approvals.registry import ApprovalRegistry
from app.services.event.app_event_bus import AppEventType, get_event_bus


@pytest.mark.asyncio
async def test_resolve_strips_allow_always_for_destructive_action(client) -> None:
    """When an approval contains an irreversible destructive flag, allow_always must be stripped."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-dest-test",
        action_type="subagent_approval",
        payload={
            "tool_calls": [{"name": "bash_code_execute_tool", "args": {"command": "rm -rf /test"}}],
            "reviewConfigs": [
                {
                    "irreversibleDestructive": True,
                    "hideAllowAlways": True,
                    "snapshotId": "snap_hash_test_123",
                }
            ],
            "snapshotId": "snap_hash_test_123",
        },
        chat_id="chat-dest-1",
        thread_id="thread-dest-1",
    )

    bus = get_event_bus()
    mock_publish = MagicMock()
    with patch.object(bus, "publish", mock_publish):
        resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={
                "decision": "approve",
                "allow_always": "session:bash_code_execute_tool",
                "ttl_seconds": 3600,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"].lower() == "approved"

        # Verify APPROVAL_RESOLVED event published has allow_always=None
        resolved_events = [
            call[0][0]
            for call in mock_publish.call_args_list
            if call[0][0].event_type == AppEventType.APPROVAL_RESOLVED
        ]
        assert len(resolved_events) == 1
        assert resolved_events[0].data.get("allow_always") is None


@pytest.mark.asyncio
async def test_rollback_approval_not_found(client) -> None:
    """Rollback on non-existent approval returns 404."""
    resp = client.post("/api/v1/approvals/non_existent_id/rollback")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rollback_approval_no_snapshot(client) -> None:
    """Rollback on approval without snapshot returns 400."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-dest-test",
        action_type="subagent_approval",
        payload={"action": "read_file"},
        chat_id="chat-dest-2",
        thread_id="thread-dest-2",
    )

    resp = client.post(f"/api/v1/approvals/{record.id}/rollback")
    assert resp.status_code == 400
    assert "workspace snapshot id" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rollback_approval_success(client) -> None:
    """Rollback successfully restores workspace from snapshot."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-dest-test",
        action_type="subagent_approval",
        payload={
            "snapshotId": "commit_stash_mock_snapshot",
        },
        chat_id="chat-dest-3",
        thread_id="thread-dest-3",
    )

    with patch(
        "app.api.approvals.router.rollback_workspace_snapshot",
        return_value=True,
    ) as mock_rollback:
        resp = client.post(
            f"/api/v1/approvals/{record.id}/rollback",
            json={"workspace_path": "/mock/workspace"},
        )
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["ok"] is True
        assert res_data["snapshot_id"] == "commit_stash_mock_snapshot"
        assert "Workspace successfully rolled back" in res_data["message"]
        mock_rollback.assert_called_once()


@pytest.mark.asyncio
async def test_rollback_approval_expired_ttl(client) -> None:
    """Rollback on approval older than 10 minutes (600s) must be rejected with 400."""
    from datetime import datetime, timedelta, timezone

    record = await ApprovalRegistry.create_approval(
        agent_id="agent-dest-test",
        action_type="subagent_approval",
        payload={
            "snapshotId": "commit_stash_old_snapshot",
        },
        chat_id="chat-dest-4",
        thread_id="thread-dest-4",
    )

    # Artificially age the record to 15 minutes ago
    fifteen_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    with patch(
        "app.services.approvals.registry.ApprovalRegistry.get_approval",
        return_value=MagicMock(
            id=record.id,
            created_at=fifteen_mins_ago,
            payload={"snapshotId": "commit_stash_old_snapshot"},
        ),
    ):
        resp = client.post(f"/api/v1/approvals/{record.id}/rollback")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()
