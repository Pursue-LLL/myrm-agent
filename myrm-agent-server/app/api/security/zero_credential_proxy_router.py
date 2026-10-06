"""FastAPI router for Enterprise Zero-Credential Proxy and Super-CLI Suite.

[INPUT]
- app.schemas.zero_credential_proxy::{RegisterProxyRuleRequest, OutboundProxyRelayRequest, SanitizeTextRequest, SuperCliExecuteRequest}
- app.services.security.zero_credential_proxy_service::{ZeroCredentialProxyService}

[OUTPUT]
- router: APIRouter for zero-credential proxy rules, relay dispatch, text sanitization, and super CLI execution.

[POS]
app/api/security router exposing zero-credential proxy routes and command execution guards.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.zero_credential_proxy import (
    OutboundProxyRelayRequest,
    OutboundProxyRelayResponse,
    ProxyRuleMetadataResponse,
    RegisterProxyRuleRequest,
    SanitizeTextRequest,
    SanitizeTextResponse,
    SuperCliExecuteRequest,
    SuperCliExecuteResponse,
)
from app.services.security.zero_credential_proxy_service import (
    ZeroCredentialProxyService,
)

router = APIRouter(
    prefix="/zero-credential-proxy",
    tags=["Zero-Credential Proxy Security"],
)


@router.post(
    "/rules",
    response_model=ProxyRuleMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new outbound proxy injection rule",
)
def register_proxy_rule(
    request: RegisterProxyRuleRequest,
) -> ProxyRuleMetadataResponse:
    """Register outbound proxy rule."""
    service = ZeroCredentialProxyService.get_instance()
    return service.register_rule(request)


@router.get(
    "/rules",
    response_model=list[ProxyRuleMetadataResponse],
    summary="List all registered proxy rules with redacted tokens",
)
def list_proxy_rules() -> list[ProxyRuleMetadataResponse]:
    """List proxy rules."""
    service = ZeroCredentialProxyService.get_instance()
    return service.list_rules()


@router.delete(
    "/rules/{rule_id}",
    response_model=dict[str, bool],
    summary="Remove a proxy injection rule",
)
def remove_proxy_rule(rule_id: str) -> dict[str, bool]:
    """Delete proxy rule."""
    service = ZeroCredentialProxyService.get_instance()
    service.remove_rule(rule_id)
    return {"success": True}


@router.post(
    "/relay",
    response_model=OutboundProxyRelayResponse,
    summary="Relay outbound HTTP request and dynamically inject credentials",
)
def relay_outbound_request(
    request: OutboundProxyRelayRequest,
) -> OutboundProxyRelayResponse:
    """Relay request from sandbox, injecting credentials at host boundary."""
    service = ZeroCredentialProxyService.get_instance()
    resp = service.relay_outbound_request(request)
    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=resp.blocked_reason or "Forbidden outbound request",
        )
    return resp


@router.post(
    "/sanitize",
    response_model=SanitizeTextResponse,
    summary="Sanitize sensitive credentials in text with model transparency notice",
)
def sanitize_text(
    request: SanitizeTextRequest,
) -> SanitizeTextResponse:
    """Scrub sensitive tokens from output streams or error tracebacks."""
    service = ZeroCredentialProxyService.get_instance()
    return service.sanitize_text(request)


@router.post(
    "/super-cli",
    response_model=SuperCliExecuteResponse,
    summary="Execute legacy CLI command with transient memory-only credentials and sanitized streams",
)
def execute_super_cli(
    request: SuperCliExecuteRequest,
) -> SuperCliExecuteResponse:
    """Execute command via Super-CLI wrapper."""
    service = ZeroCredentialProxyService.get_instance()
    return service.execute_super_cli(request)
