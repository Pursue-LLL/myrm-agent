"""Service layer for Secretless Credential Egress Proxy and Placeholder Swap Suite.

[INPUT]
- myrm_agent_harness.core.security.secretless_egress_proxy::SwapOnAccessProxy, PlaceholderRegistry
- app.schemas.secretless_egress_proxy::BoundCredentialRegisterRequest, InspectSwapRequest

[OUTPUT]
- SecretlessEgressProxyService, get_secretless_egress_proxy_service

[POS]
Business service managing domain-bound secrets, outbound swap inspection, and revocation.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.secretless_egress_proxy import (
    BoundCredentialSpec,
    PlaceholderRegistry,
    ProxyInspectionResult,
    SwapEvent,
    SwapOnAccessProxy,
)

from app.schemas.secretless_egress_proxy import (
    BoundCredentialRegisterRequest,
    BoundCredentialResponse,
    InspectSwapRequest,
    InspectSwapResponse,
    RevokeCredentialResponse,
    SwapEventResponse,
)

logger = logging.getLogger(__name__)


def _to_event_response(event: SwapEvent | None) -> SwapEventResponse | None:
    if event is None:
        return None
    return SwapEventResponse(
        timestamp=event.timestamp,
        target_host=event.target_host,
        path=event.path,
        method=event.method,
        placeholder_used=event.placeholder_used,
        is_swapped=event.is_swapped,
        is_blocked=event.is_blocked,
        block_reason=event.block_reason,
    )


def _to_credential_response(spec: BoundCredentialSpec) -> BoundCredentialResponse:
    return BoundCredentialResponse(
        target_host=spec.target_host,
        auth_header_name=spec.auth_header_name,
        auth_header_template=spec.auth_header_template,
        placeholder=spec.placeholder,
        is_active=spec.is_active,
    )


class SecretlessEgressProxyService:
    """Manages L7 egress proxy inspection and host-bound placeholder swapping."""

    def __init__(self, proxy: SwapOnAccessProxy | None = None) -> None:
        self._proxy = proxy or SwapOnAccessProxy(PlaceholderRegistry())

    @property
    def proxy(self) -> SwapOnAccessProxy:
        return self._proxy

    def register_credential(
        self, req: BoundCredentialRegisterRequest
    ) -> BoundCredentialResponse:
        """Register a real credential outside sandbox and bind random placeholder."""
        spec = self._proxy.registry.register_credential(
            target_host=req.target_host,
            real_secret=req.real_secret,
            auth_header_name=req.auth_header_name,
            auth_header_template=req.auth_header_template,
        )
        logger.info(
            "Registered secretless credential for host '%s' with placeholder '%s'",
            spec.target_host,
            spec.placeholder,
        )
        return _to_credential_response(spec)

    def revoke_credential(self, target_host: str) -> RevokeCredentialResponse:
        """Revoke a bound credential for target host."""
        success = self._proxy.registry.revoke_credential(target_host)
        logger.info("Revoked secretless credential for host '%s': %s", target_host, success)
        return RevokeCredentialResponse(success=success, target_host=target_host)

    def list_credentials(self) -> list[BoundCredentialResponse]:
        """List all active bound credentials."""
        specs = self._proxy.registry.list_active()
        return [_to_credential_response(spec) for spec in specs]

    def inspect_and_swap(self, req: InspectSwapRequest) -> InspectSwapResponse:
        """Inspect outbound request from sandbox and swap placeholder if authorized."""
        result: ProxyInspectionResult = self._proxy.inspect_and_swap(
            target_host=req.target_host,
            path=req.path,
            method=req.method,
            headers=req.headers,
        )
        return InspectSwapResponse(
            is_allowed=result.is_allowed,
            status_code=result.status_code,
            headers_to_inject=result.headers_to_inject,
            reason=result.reason,
            event=_to_event_response(result.event),
        )

    def get_audit_events(self, limit: int = 50) -> list[SwapEventResponse]:
        """Fetch audit trail of egress inspection and swap attempts."""
        events = self._proxy.get_audit_events()
        slice_events = events[-limit:] if limit > 0 else events
        res: list[SwapEventResponse] = []
        for ev in slice_events:
            converted = _to_event_response(ev)
            if converted is not None:
                res.append(converted)
        return res


_service_instance: SecretlessEgressProxyService | None = None


def get_secretless_egress_proxy_service() -> SecretlessEgressProxyService:
    """Retrieve singleton instance of SecretlessEgressProxyService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SecretlessEgressProxyService()
    return _service_instance
