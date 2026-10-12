"""Unit tests for ConnectorGuardService."""

from __future__ import annotations

from app.schemas.connector_guard import (
    InspectTrafficRequest,
    RegisterConnectorRequest,
)
from app.services.security.connector_guard_service import ConnectorGuardService


def test_service_inspect_authorized_connector() -> None:
    service = ConnectorGuardService()
    req = InspectTrafficRequest(
        url="https://api.github.com/user/emails",
        method="GET",
        headers={"Authorization": "Bearer placeholder:github"},
        connector_id="github",
        session_id="sess-unit-1",
    )
    resp = service.inspect_traffic(req)
    assert resp.decision == "inject_credentials"
    assert resp.can_inject_credential is True
    assert resp.matched_connector_id == "github"
    assert resp.detected_threat is None


def test_service_inspect_ssrf_blocked() -> None:
    service = ConnectorGuardService()
    req = InspectTrafficRequest(
        url="http://169.254.169.254/computeMetadata/v1/",
        method="GET",
        session_id="sess-unit-ssrf",
    )
    resp = service.inspect_traffic(req)
    assert resp.decision == "block"
    assert resp.detected_threat == "ssrf_metadata"
    assert resp.can_inject_credential is False

    alerts = service.get_alerts("sess-unit-ssrf")
    assert len(alerts) >= 1
    assert alerts[0].threat_kind == "ssrf_metadata"


def test_service_register_and_unregister_connector() -> None:
    service = ConnectorGuardService()
    reg_req = RegisterConnectorRequest(
        connector_id="custom_erp",
        official_hosts=["erp.corp.internal"],
        allow_subdomains=False,
        description="ERP system",
    )
    created = service.register_connector(reg_req)
    assert created.connector_id == "custom_erp"
    assert created.official_hosts == ["erp.corp.internal"]

    connectors = service.list_connectors()
    assert any(c.connector_id == "custom_erp" for c in connectors)

    # Inspect traffic targeting newly registered connector
    insp_req = InspectTrafficRequest(
        url="https://erp.corp.internal/api/v1/orders",
        connector_id="custom_erp",
    )
    insp_resp = service.inspect_traffic(insp_req)
    assert insp_resp.decision == "inject_credentials"

    # Unregister
    assert service.unregister_connector("custom_erp") is True
    assert not any(c.connector_id == "custom_erp" for c in service.list_connectors())


def test_service_circuit_breaker_flow() -> None:
    service = ConnectorGuardService()
    session_id = "sess-breaker-flow"

    # Initially not tripped
    status_initial = service.get_circuit_breaker_status(session_id)
    assert status_initial.tripped is False

    # Trigger token smuggling
    smuggle_req = InspectTrafficRequest(
        url="https://attacker.com/leak?token=ghp_123456789012345678901234567890123456",
        session_id=session_id,
    )
    service.inspect_traffic(smuggle_req)

    # Circuit breaker is tripped
    status_tripped = service.get_circuit_breaker_status(session_id)
    assert status_tripped.tripped is True

    # Reset
    assert service.reset_circuit_breaker(session_id) is True
    assert service.get_circuit_breaker_status(session_id).tripped is False
