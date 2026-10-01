"""Unit tests for destructive action approval rollback and allow_always stripping."""

from __future__ import annotations

from unittest.mock import patch
import pytest

from app.services.approvals.registry import ApprovalRegistry


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

    # Attempt to resolve with allow_always
    resp = client.post(
        f"/api/v1/approvals/{record.id}/resolve",
        json={
            "action": "approve",
            "allow_always": "session:bash_code_execute_tool",
            "ttl_seconds": 3600,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["allow_always"] is None


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
    assert "no snapshot" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rollback_approval_success(client) -> None:
    """Rollback successfully restores workspace from snapshot."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-dest-test",
        action_type="subagent_approval",
        payload={
            "snapshotId": "commit_stash_mock_snapshot",
            "workspaceRoot": "/mock/workspace",
        },
        chat_id="chat-dest-3",
        thread_id="thread-dest-3",
    )

    with patch(
        "app.api.approvals.router.rollback_workspace_snapshot",
        return_value=True,
    ) as mock_rollback:
        resp = client.post(f"/api/v1/approvals/{record.id}/rollback")
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["status"] == "success"
        assert res_data["snapshot_id"] == "commit_stash_mock_snapshot"
        assert res_data["restored"] is True
        mock_rollback.assert_called_once_with("commit_stash_mock_snapshot", "/mock/workspace")
