"""Unit tests for ManagedPermissionRollbackService."""

from __future__ import annotations

import pytest

from app.schemas.managed_permission_rollback import (
    ComplianceDriftCheckRequest,
    CreateSessionCheckpointRequest,
    RegisterConnectorRequest,
    RollbackSessionCheckpointRequest,
)
from app.services.security.managed_permission_rollback_service import (
    ManagedPermissionRollbackService,
    get_managed_permission_rollback_service,
)


@pytest.fixture
def service() -> ManagedPermissionRollbackService:
    return ManagedPermissionRollbackService()


def test_singleton_getter() -> None:
    svc1 = get_managed_permission_rollback_service()
    svc2 = get_managed_permission_rollback_service()
    assert svc1 is svc2


def test_list_and_get_presets(service: ManagedPermissionRollbackService) -> None:
    presets = service.list_presets()
    assert len(presets) == 4
    roles = {p.role for p in presets}
    assert "AUDITOR" in roles
    assert "SAFE_COLLABORATOR" in roles
    assert "FULL_STACK_DEVELOPER" in roles
    assert "AUTONOMOUS_OPS" in roles

    # Get single preset
    auditor = service.get_preset("AUDITOR")
    assert auditor.role == "AUDITOR"
    assert auditor.allow_shell_execution is False
    assert auditor.rules["TOOLS"] == "DENY"


def test_check_compliance_drift(service: ManagedPermissionRollbackService) -> None:
    # 1. Compliant configuration
    req_compliant = ComplianceDriftCheckRequest(
        agent_id="agent_assistant",
        assigned_role="SAFE_COLLABORATOR",
        active_rules={
            "TOOLS": "ASK_HUMAN",
            "FILES": "ALWAYS_ALLOW",
            "APIS": "ASK_HUMAN",
            "SENDS": "ASK_HUMAN",
        },
        active_allow_shell=False,
    )
    res_compliant = service.check_compliance_drift(req_compliant)
    assert res_compliant.is_compliant is True
    assert res_compliant.drift_score == 0.0
    assert len(res_compliant.deviations) == 0

    # 2. Rogue drift
    req_drift = ComplianceDriftCheckRequest(
        agent_id="agent_rogue",
        assigned_role="SAFE_COLLABORATOR",
        active_rules={
            "TOOLS": "ALWAYS_ALLOW",  # excessive
            "FILES": "ALWAYS_ALLOW",
            "APIS": "ALWAYS_ALLOW",  # excessive
            "SENDS": "ALWAYS_ALLOW",  # excessive
        },
        active_allow_shell=True,  # excessive
    )
    res_drift = service.check_compliance_drift(req_drift)
    assert res_drift.is_compliant is False
    assert res_drift.drift_score > 0.0
    assert len(res_drift.deviations) >= 4


def test_checkpoint_lifecycle_and_rollback(
    service: ManagedPermissionRollbackService,
) -> None:
    session_id = "sess_checkout_test"

    # 1. Create checkpoint
    req_create = CreateSessionCheckpointRequest(
        session_id=session_id,
        label="Initial verified state",
        files={
            "main.py": "def run(): return 42\n",
            "settings.toml": "debug = false\n",
        },
        memory_state={"status": "step_1_done"},
        active_role="FULL_STACK_DEVELOPER",
    )
    ckpt = service.create_checkpoint(req_create)
    assert ckpt.session_id == session_id
    assert ckpt.files_count == 2
    assert ckpt.memory_keys_count == 1

    # 2. List checkpoints
    ckpts = service.list_checkpoints(session_id)
    assert len(ckpts) == 1
    assert ckpts[0].checkpoint_id == ckpt.checkpoint_id

    # 3. Simulate drift and perform rollback
    req_rollback = RollbackSessionCheckpointRequest(
        checkpoint_id=ckpt.checkpoint_id,
        current_files={
            "main.py": "syntax error bad code",
            "temp_junk.txt": "delete me",
        },
    )
    rollback_res = service.rollback_checkpoint(req_rollback)
    assert rollback_res.checkpoint_id == ckpt.checkpoint_id
    assert rollback_res.reverted_files_count >= 2
    assert "main.py" in rollback_res.restored_files
    assert rollback_res.restored_files["main.py"] == "def run(): return 42\n"
    assert "temp_junk.txt" not in rollback_res.restored_files
    assert rollback_res.restored_memory_state["status"] == "step_1_done"


def test_managed_connectors_hub(service: ManagedPermissionRollbackService) -> None:
    # 1. Register connector
    req_reg = RegisterConnectorRequest(
        connector_id="slack-dev-bot",
        channel_type="SLACK",
        display_name="Slack Dev Channel Relay",
        account_identifier="T12345/C67890",
        token_lifetime_seconds=3600.0,
    )
    conn = service.register_connector(req_reg)
    assert conn.connector_id == "slack-dev-bot"
    assert conn.channel_type == "SLACK"
    assert conn.status == "ACTIVE"

    # 2. Record heartbeat
    hb = service.record_connector_heartbeat("slack-dev-bot")
    assert hb is not None
    assert hb.status == "ACTIVE"

    # 3. List connectors
    conns = service.list_connectors()
    assert len(conns) >= 1
    assert any(c.connector_id == "slack-dev-bot" for c in conns)
