"""Unit tests for SagaDualEngineService."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.saga_dual_engine import (
    ConnectorUntrustedError,
    EmissionUnconfirmedError,
)

from app.schemas.saga_dual_engine import (
    ExecuteDualToolRequest,
    GrantTrustLeaseRequest,
    RevokeTrustLeaseRequest,
)
from app.services.security.saga_dual_engine_service import SagaDualEngineService


def test_acquisition_execution_lifecycle() -> None:
    service = SagaDualEngineService()

    resp = service.execute_tool(
        ExecuteDualToolRequest(
            tool_name="read_documentation",
            intent="ACQUISITION",
            params={"topic": "api_specs"},
            agent_id="agent_doc",
        )
    )

    assert resp.tool_name == "read_documentation"
    assert resp.intent == "ACQUISITION"
    assert "Executed read_documentation" in resp.output
    assert resp.audit_record is None


def test_emission_connector_trust_and_hitl_gates() -> None:
    service = SagaDualEngineService()

    # 1. Emission without trust lease is rejected
    req = ExecuteDualToolRequest(
        tool_name="execute_wire_transfer",
        intent="EMISSION",
        params={"amount": 5000},
        agent_id="agent_finance",
        connector_id="bank_api",
        connector_host="api.bank.corp",
        required_scope="transfers:execute",
        hitl_confirmed=True,
    )
    with pytest.raises(ConnectorUntrustedError, match="is UNTRUSTED"):
        service.execute_tool(req)

    # 2. Grant trust lease
    lease = service.grant_lease(
        GrantTrustLeaseRequest(
            connector_id="bank_api",
            host="api.bank.corp",
            authorized_scopes=["transfers:execute"],
            ttl_seconds=1800,
        )
    )
    assert lease.is_active is True

    # 3. Emission with trust lease but WITHOUT HITL confirmation is rejected
    req_no_hitl = ExecuteDualToolRequest(
        tool_name="execute_wire_transfer",
        intent="EMISSION",
        params={"amount": 5000},
        agent_id="agent_finance",
        connector_id="bank_api",
        connector_host="api.bank.corp",
        required_scope="transfers:execute",
        hitl_confirmed=False,
    )
    with pytest.raises(EmissionUnconfirmedError, match="requires explicit secondary HITL confirmation"):
        service.execute_tool(req_no_hitl)

    # 4. Emission with both trust lease AND HITL confirmation succeeds
    resp = service.execute_tool(req)
    assert resp.intent == "EMISSION"
    assert resp.audit_record is not None
    assert resp.audit_record.connector_id == "bank_api"

    # 5. Check audit log
    audit_log = service.get_audit_log()
    assert len(audit_log) >= 1
    assert any(r.connector_id == "bank_api" for r in audit_log)


def test_saga_rollback_and_lease_revocation() -> None:
    service = SagaDualEngineService()

    # Grant lease
    lease = service.grant_lease(
        GrantTrustLeaseRequest(
            connector_id="crm_api",
            host="crm.corp.internal",
            authorized_scopes=["write"],
        )
    )

    # Execute emission with compensator hook
    service.execute_tool(
        ExecuteDualToolRequest(
            tool_name="create_lead",
            intent="EMISSION",
            params={"email": "lead@company.com"},
            agent_id="agent_sales",
            connector_id="crm_api",
            connector_host="crm.corp.internal",
            hitl_confirmed=True,
            compensator_name="delete_lead",
            compensation_params={"email": "lead@company.com"},
        )
    )

    # Trigger Saga Rollback
    rollback_res = service.rollback_saga()
    assert rollback_res.total_steps_rolled_back >= 1
    assert rollback_res.success is True

    # Revoke lease
    rev_res = service.revoke_lease(RevokeTrustLeaseRequest(lease_id=lease.lease_id))
    assert rev_res.revoked is True
