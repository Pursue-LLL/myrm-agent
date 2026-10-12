"""Unit tests for TripartiteLedgerService."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.tripartite_ledger import (
    ActionSemanticViolationError,
    PreIOAuditAssertionError,
)

from app.schemas.tripartite_ledger import (
    ActionSemanticExecutionRequest,
    AppendAuditRecordRequest,
    AuditQueryRequest,
    OpsForceStopRequest,
    OpsRegisterTaskRequest,
)
from app.services.security.tripartite_ledger_service import TripartiteLedgerService


def test_tripartite_ledger_service_lifecycle() -> None:
    service = TripartiteLedgerService()

    # 1. Append record with connector invocation 4 questions
    append_req = AppendAuditRecordRequest(
        who_user_id="user_admin",
        who_agent_id="agent_orchestrator",
        rule_version_hash="rule_hash_v1",
        tool_name="mcp__postgres__execute_query",
        tool_args={"query": "SELECT * FROM users", "password": "super_secret_db_password"},
        connector_source="mcp__postgres",
        connector_scope="db:read",
        authorized_parameters=["query"],
        reconcile_receipt="rcpt_pg_101",
    )
    rec_dto = service.append_record(append_req)
    assert rec_dto.sequence_number == 0
    assert rec_dto.sanitized_args_snapshot["password"] == "[REDACTED_SECRET]"
    assert rec_dto.sanitized_args_snapshot["query"] == "SELECT * FROM users"

    # 2. Verify hash chain
    v_res = service.verify_ledger()
    assert v_res.is_valid is True
    assert v_res.total_records == 1

    # 3. Query records
    query_res = service.query_records(
        AuditQueryRequest(connector_source="mcp__postgres", who_agent_id="agent_orchestrator")
    )
    assert query_res.total_matched == 1
    assert query_res.records[0].tool_name == "mcp__postgres__execute_query"


def test_semantic_execution_scenarios() -> None:
    service = TripartiteLedgerService()

    # 1. REPLAY_LOG blocks tool execution
    with pytest.raises(ActionSemanticViolationError):
        service.execute_semantic_action(
            ActionSemanticExecutionRequest(
                mode="REPLAY_LOG",
                tool_name="execute_payment",
            )
        )

    # 2. OFFLINE_EVAL simulates side-effect
    res_eval = service.execute_semantic_action(
        ActionSemanticExecutionRequest(
            mode="OFFLINE_EVAL",
            tool_name="create_database",
        )
    )
    assert res_eval.is_simulated is True
    assert res_eval.executed is False

    # 3. RE_EXECUTE unconfirmed fails
    with pytest.raises(ActionSemanticViolationError):
        service.execute_semantic_action(
            ActionSemanticExecutionRequest(
                mode="RE_EXECUTE",
                tool_name="live_deploy",
                explicit_confirmed=False,
            )
        )

    # 4. RE_EXECUTE without pre-I/O audit record fails
    with pytest.raises(PreIOAuditAssertionError):
        service.execute_semantic_action(
            ActionSemanticExecutionRequest(
                mode="RE_EXECUTE",
                tool_name="live_deploy",
                explicit_confirmed=True,
                audit_record_id="aud_unknown",
            )
        )

    # 5. RE_EXECUTE with pre-I/O audit record succeeds
    rec = service.append_record(
        AppendAuditRecordRequest(
            who_user_id="user_admin",
            who_agent_id="agent_deployer",
            rule_version_hash="rules_v2",
            tool_name="live_deploy",
            tool_args={"env": "prod"},
            connector_source="mcp__k8s",
            connector_scope="deploy",
            authorized_parameters=["env"],
            reconcile_receipt="pre_rec_deploy_ok",
        )
    )
    res_exec = service.execute_semantic_action(
        ActionSemanticExecutionRequest(
            mode="RE_EXECUTE",
            tool_name="live_deploy",
            explicit_confirmed=True,
            audit_record_id=rec.record_id,
        )
    )
    assert res_exec.executed is True
    assert res_exec.is_simulated is False


def test_zero_knowledge_ops_service() -> None:
    service = TripartiteLedgerService()

    # Register task
    t_dto = service.register_task(
        OpsRegisterTaskRequest(
            task_id="task_99",
            agent_id="agent_worker",
            memory_bytes=4096000,
        )
    )
    assert t_dto.task_id == "task_99"
    assert t_dto.state == "RUNNING"

    # Force stop
    stop_res = service.ops_force_stop(
        OpsForceStopRequest(task_id="task_99", operator_id="ops_engineer")
    )
    assert stop_res.stopped is True

    # Check updated telemetry
    updated = service.get_ops_telemetry("task_99")
    assert updated.state == "STOPPED_BY_OPS"
