"""Service layer for Connector Host Allowlist and Anti-Exfiltration SSRF Guard.

[INPUT]
- myrm_agent_harness.core.security.connector_guard::{AntiExfiltrationGuard, ConnectorAllowlistEntry, EnterpriseOutboundMode, OutboundTrafficInspection}
- app.schemas.connector_guard::{InspectTrafficRequest, InspectTrafficResponse, RegisterConnectorRequest, ConnectorEntryResponse, ThreatAlertResponse, CircuitBreakerStatusResponse}

[OUTPUT]
- ConnectorGuardService, get_connector_guard_service: service managing connector traffic inspection, allowlists, and circuit breakers.

[POS]
app/services/security service wrapping harness connector host allowlist and SSRF guard.
"""

from __future__ import annotations

import logging
from typing import cast

from myrm_agent_harness.core.security.connector_guard import (
    AntiExfiltrationGuard,
    ConnectorAllowlistEntry,
    EnterpriseOutboundMode,
    OutboundTrafficInspection,
)

from app.schemas.connector_guard import (
    CircuitBreakerStatusResponse,
    ConnectorEntryResponse,
    InspectTrafficRequest,
    InspectTrafficResponse,
    RegisterConnectorRequest,
    ThreatAlertResponse,
)

logger = logging.getLogger(__name__)


class ConnectorGuardService:
    """Manages connector allowlists, outbound traffic vetting, SSRF detection, and circuit breaking."""

    def __init__(self, guard: AntiExfiltrationGuard | None = None) -> None:
        self.guard = guard or AntiExfiltrationGuard()

    def inspect_traffic(
        self, req: InspectTrafficRequest
    ) -> InspectTrafficResponse:
        """Vet an outbound request against SSRF rules and connector host allowlists."""
        traffic = OutboundTrafficInspection(
            url=req.url,
            method=req.method,
            headers=req.headers,
            query_params=req.query_params,
            connector_id=req.connector_id,
            session_id=req.session_id,
        )
        result = self.guard.inspect_traffic(traffic)
        return InspectTrafficResponse(
            decision=result.decision.value,
            reason=result.reason,
            detected_threat=result.detected_threat.value if result.detected_threat else None,
            sanitized_headers=result.sanitized_headers,
            can_inject_credential=result.can_inject_credential,
            matched_connector_id=result.matched_connector_id,
        )

    def register_connector(
        self, req: RegisterConnectorRequest
    ) -> ConnectorEntryResponse:
        """Register or update an authorized connector endpoint allowlist."""
        entry = ConnectorAllowlistEntry(
            connector_id=req.connector_id,
            official_hosts=tuple(req.official_hosts),
            allow_subdomains=req.allow_subdomains,
            allowed_schemes=tuple(req.allowed_schemes),
            description=req.description,
        )
        self.guard.registry.register(entry)
        return ConnectorEntryResponse(
            connector_id=entry.connector_id,
            official_hosts=list(entry.official_hosts),
            allow_subdomains=entry.allow_subdomains,
            allowed_schemes=list(entry.allowed_schemes),
            description=entry.description,
        )

    def unregister_connector(self, connector_id: str) -> bool:
        """Remove a connector from the allowlist registry."""
        return self.guard.registry.unregister(connector_id)

    def list_connectors(self) -> list[ConnectorEntryResponse]:
        """List all registered connector entries."""
        entries = self.guard.registry.list_entries()
        return [
            ConnectorEntryResponse(
                connector_id=e.connector_id,
                official_hosts=list(e.official_hosts),
                allow_subdomains=e.allow_subdomains,
                allowed_schemes=list(e.allowed_schemes),
                description=e.description,
            )
            for e in entries
        ]

    def get_alerts(self, session_id: str | None = None) -> list[ThreatAlertResponse]:
        """Return captured security alerts."""
        alerts = self.guard.get_alerts(session_id)
        return [
            ThreatAlertResponse(
                alert_id=a.alert_id,
                session_id=a.session_id,
                url=a.url,
                threat_kind=a.threat_kind.value,
                description=a.description,
                blocked=a.blocked,
                timestamp=a.timestamp,
            )
            for a in alerts
        ]

    def reset_circuit_breaker(self, session_id: str) -> bool:
        """Reset tripped circuit breaker for a given session."""
        return self.guard.reset_circuit_breaker(session_id)

    def get_circuit_breaker_status(
        self, session_id: str
    ) -> CircuitBreakerStatusResponse:
        """Query circuit breaker status for a given session."""
        tripped = self.guard.is_circuit_breaker_tripped(session_id)
        return CircuitBreakerStatusResponse(session_id=session_id, tripped=tripped)

    def set_outbound_mode(self, mode_str: str) -> str:
        """Set enterprise outbound policy mode."""
        mode = EnterpriseOutboundMode(mode_str)
        self.guard.mode = cast(EnterpriseOutboundMode, mode)
        return self.guard.mode.value


_singleton_service: ConnectorGuardService | None = None


def get_connector_guard_service() -> ConnectorGuardService:
    """Retrieve singleton instance of ConnectorGuardService."""
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = ConnectorGuardService()
    return _singleton_service
