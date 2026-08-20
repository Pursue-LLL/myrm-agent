"""Browser Extension Bridge API endpoints.

[INPUT]
- app.services.extension.bridge::get_extension_bridge (POS: singleton bridge instance)

[OUTPUT]
- ws_router: WebSocket endpoint for extension connection (ws://.../api/ws/extension)
- router: REST endpoints for domain authorization and setup hints (includes clip-agent sub-router)

[POS]
API layer for the browser extension bridge. WebSocket for MV3 persistent connection;
REST for authorized domains, connection status, and setup hints. Wiki clip agent scope
lives in routes/clip_agent.py.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field

from app.services.extension.bridge import DomainPolicyWarning, get_extension_bridge

logger = logging.getLogger(__name__)

router = APIRouter()
ws_router = APIRouter()


# --- WebSocket Endpoint ---


def _is_allowed_extension_origin(origin: str | None) -> bool:
    """Allow Chrome extension origins and origin-less diagnostics."""
    if origin is None:
        return True
    normalized = origin.strip().lower()
    return normalized == "" or normalized.startswith("chrome-extension://")


@ws_router.websocket("/extension")
async def extension_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """WebSocket endpoint for browser extension connection.

    The extension connects here and maintains a persistent WebSocket
    for receiving commands and sending CDP data back.

    Query params:
        token: Authentication token (validated against server's extension_auth_token)
    """
    from app.config.deploy_mode import is_webui_remote_mode
    from app.config.settings import settings

    origin = websocket.headers.get("origin")
    if not _is_allowed_extension_origin(origin):
        logger.warning("Rejected extension WS: forbidden origin=%s", origin)
        await websocket.close(code=4003, reason="Forbidden origin")
        return

    expected_token = settings.extension_auth_token.get_secret_value()
    if is_webui_remote_mode() and not expected_token:
        logger.error("Rejected extension WS: EXTENSION_AUTH_TOKEN is required in remote mode")
        await websocket.close(code=4002, reason="Extension auth token required in remote mode")
        return

    if expected_token and token != expected_token:
        logger.warning("Rejected extension WS: invalid token provided")
        await websocket.close(code=4001, reason="Invalid token")
        return

    bridge = get_extension_bridge()
    await bridge.handle_ws_connection(websocket)


# --- REST Endpoints ---


class ExtensionTabResponse(BaseModel):
    """Single tab exposed by extension."""

    tab_id: int
    url: str
    title: str
    domain: str
    active: bool = False


class ExtensionStatusResponse(BaseModel):
    """Extension connection status."""

    connected: bool = False
    handshake_ready: bool = False
    relay_cdp_ready: bool = False
    extension_version: str = ""
    browser_name: str = ""
    authorized_domains: list[str] = Field(default_factory=list)
    allow_all_eligible_tabs: bool = False
    paused_tab_ids: list[int] = Field(default_factory=list)
    access_policy_valid: bool = False
    available_tabs: list[ExtensionTabResponse] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class DomainsUpdateRequest(BaseModel):
    """Request to update authorized domains."""

    domains: list[str] = Field(
        ...,
        description="List of domain patterns to authorize (e.g., ['github.com', '*.google.com'])",
    )


class AccessPolicyUpdateRequest(BaseModel):
    """Request to update extension tab access policy."""

    allow_all_eligible_tabs: bool = False
    domains: list[str] = Field(default_factory=list)
    paused_tab_ids: list[int] = Field(default_factory=list)


class AccessPolicyResponse(BaseModel):
    """Current extension tab access policy."""

    allow_all_eligible_tabs: bool = False
    authorized_domains: list[str] = Field(default_factory=list)
    paused_tab_ids: list[int] = Field(default_factory=list)
    policy_valid: bool = False
    warnings: list[DomainPolicyWarningResponse] = Field(default_factory=list)


class DomainPolicyWarningResponse(BaseModel):
    """Structured warning for domain authorization semantics."""

    code: Literal["wildcard_includes_root"]
    pattern: str
    root_domain: str


class DomainsUpdateResponse(BaseModel):
    """Response after domain update."""

    authorized_domains: list[str]
    warnings: list[DomainPolicyWarningResponse] = Field(default_factory=list)


def _to_warning_responses(
    warnings: list[DomainPolicyWarning],
) -> list[DomainPolicyWarningResponse]:
    return [
        DomainPolicyWarningResponse(
            code="wildcard_includes_root",
            pattern=warning.pattern,
            root_domain=warning.root_domain,
        )
        for warning in warnings
    ]


@router.get("/extension/status", response_model=ExtensionStatusResponse)
async def get_extension_status() -> ExtensionStatusResponse:
    """Get current browser extension connection status."""
    bridge = get_extension_bridge()
    status = await bridge.get_status()
    policy = bridge.get_access_policy()
    relay_ready = await bridge.relay_cdp_ready()
    return ExtensionStatusResponse(
        connected=status.connected,
        handshake_ready=status.handshake_ready,
        relay_cdp_ready=relay_ready,
        extension_version=status.extension_version,
        browser_name=status.browser_name,
        authorized_domains=status.authorized_domains,
        allow_all_eligible_tabs=policy.allow_all_eligible_tabs,
        paused_tab_ids=sorted(policy.paused_tab_ids),
        access_policy_valid=bridge.is_access_policy_valid(),
        capabilities=status.capabilities,
        available_tabs=[
            ExtensionTabResponse(
                tab_id=t.tab_id,
                url=t.url,
                title=t.title,
                domain=t.domain,
                active=t.active,
            )
            for t in status.available_tabs
        ],
    )


@router.get("/extension/access-policy", response_model=AccessPolicyResponse)
async def get_extension_access_policy() -> AccessPolicyResponse:
    """Get extension tab access policy (domains, allow-all, paused tabs)."""
    bridge = get_extension_bridge()
    policy = bridge.get_access_policy()
    warnings = bridge.analyze_domain_policy_warnings(policy.authorized_domains)
    return AccessPolicyResponse(
        allow_all_eligible_tabs=policy.allow_all_eligible_tabs,
        authorized_domains=list(policy.authorized_domains),
        paused_tab_ids=sorted(policy.paused_tab_ids),
        policy_valid=bridge.is_access_policy_valid(),
        warnings=_to_warning_responses(warnings),
    )


@router.put("/extension/access-policy", response_model=AccessPolicyResponse)
async def update_extension_access_policy(
    body: AccessPolicyUpdateRequest,
) -> AccessPolicyResponse:
    """Update extension tab access policy and push to the connected extension."""
    bridge = get_extension_bridge()
    policy = await bridge.set_access_policy(
        allow_all_eligible_tabs=body.allow_all_eligible_tabs,
        authorized_domains=body.domains,
        paused_tab_ids=body.paused_tab_ids,
    )
    warnings = bridge.analyze_domain_policy_warnings(policy.authorized_domains)
    return AccessPolicyResponse(
        allow_all_eligible_tabs=policy.allow_all_eligible_tabs,
        authorized_domains=list(policy.authorized_domains),
        paused_tab_ids=sorted(policy.paused_tab_ids),
        policy_valid=bridge.is_access_policy_valid(),
        warnings=_to_warning_responses(warnings),
    )


@router.get("/extension/domains", response_model=DomainsUpdateResponse)
async def get_authorized_domains() -> DomainsUpdateResponse:
    """Get the list of authorized domains for extension control."""
    bridge = get_extension_bridge()
    domains = bridge.get_authorized_domains()
    warnings = bridge.analyze_domain_policy_warnings(domains)
    return DomainsUpdateResponse(
        authorized_domains=domains,
        warnings=_to_warning_responses(warnings),
    )


@router.put("/extension/domains", response_model=DomainsUpdateResponse)
async def update_authorized_domains(
    body: DomainsUpdateRequest,
) -> DomainsUpdateResponse:
    """Update the list of authorized domains for extension control.

    Only tabs on authorized domains can be controlled by the Agent.
    This is a security boundary — the user explicitly grants per-domain access.
    """
    bridge = get_extension_bridge()
    await bridge.set_authorized_domains(body.domains)
    domains = bridge.get_authorized_domains()
    warnings = bridge.analyze_domain_policy_warnings(domains)
    return DomainsUpdateResponse(
        authorized_domains=domains,
        warnings=_to_warning_responses(warnings),
    )


@router.get("/extension/tabs", response_model=list[ExtensionTabResponse])
async def list_extension_tabs() -> list[ExtensionTabResponse]:
    """List available tabs from the connected extension."""
    bridge = get_extension_bridge()
    tabs = await bridge.list_tabs()
    return [
        ExtensionTabResponse(
            tab_id=t.tab_id,
            url=t.url,
            title=t.title,
            domain=t.domain,
            active=t.active,
        )
        for t in tabs
    ]


@router.post("/extension/disconnect")
async def disconnect_extension() -> dict[str, str]:
    """Manually disconnect the browser extension."""
    bridge = get_extension_bridge()
    await bridge.disconnect()
    return {"status": "disconnected"}


class ExtensionSetupHintsResponse(BaseModel):
    """Non-secret setup hints for the browser extension popup."""

    auth_token_configured: bool = Field(
        description="True when EXTENSION_AUTH_TOKEN is set on the server",
    )
    auth_token_required: bool = Field(
        description="True when current deploy mode requires EXTENSION_AUTH_TOKEN",
    )
    cdp_endpoint_discovered: bool = Field(
        description="True when server can discover a direct local Chrome CDP endpoint",
    )
    relay_cdp_ready: bool = Field(
        description="True when extension CDP relay is ready for Playwright automation",
    )
    access_policy_valid: bool = Field(
        description="True when domains are configured or allow-all is enabled",
    )


def _build_extension_ws_url(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/api/v1/ws/extension"


class PairingCreateResponse(BaseModel):
    code: str
    expires_in: int
    ws_url: str
    http_base: str = Field(description="HTTP origin for extension pairing fetch")
    consume_url: str = Field(description="POST endpoint to exchange pairing code")


class PairingConsumeRequest(BaseModel):
    code: str = Field(min_length=1)


class PairingConsumeResponse(BaseModel):
    ws_url: str
    auth_token: str
    http_base: str = ""


def _pairing_client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _consume_pairing_or_404(code: str) -> PairingConsumeResponse:
    from app.services.extension.pairing import consume_pairing_ticket

    ticket = consume_pairing_ticket(code)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Pairing code invalid or expired")
    ws_url = ticket.ws_url
    http_base = ws_url.replace("wss://", "https://").replace("ws://", "http://")
    http_base = http_base.split("/api/v1/ws/extension")[0].rstrip("/")
    return PairingConsumeResponse(
        ws_url=ws_url,
        auth_token=ticket.auth_token,
        http_base=http_base,
    )


@router.post("/extension/pairing", response_model=PairingCreateResponse)
async def create_extension_pairing(request: Request) -> PairingCreateResponse:
    """Create a one-time pairing code for the browser extension popup."""
    from app.config.settings import settings
    from app.services.extension.pairing import create_pairing_ticket

    http_base = str(request.base_url).rstrip("/")
    ws_url = _build_extension_ws_url(request)
    token = settings.extension_auth_token.get_secret_value()
    code, expires_in = create_pairing_ticket(ws_url=ws_url, auth_token=token)
    consume_url = f"{http_base}/api/v1/extension/pairing/consume"
    return PairingCreateResponse(
        code=code,
        expires_in=int(expires_in),
        ws_url=ws_url,
        http_base=http_base,
        consume_url=consume_url,
    )


@router.post("/extension/pairing/consume", response_model=PairingConsumeResponse)
async def consume_extension_pairing_post(
    request: Request,
    body: PairingConsumeRequest,
) -> PairingConsumeResponse:
    """Exchange a one-time pairing code for extension connection settings."""
    from app.services.extension.pairing import check_pairing_rate_limit

    if not check_pairing_rate_limit(_pairing_client_key(request)):
        raise HTTPException(status_code=429, detail="Too many pairing attempts")
    return _consume_pairing_or_404(body.code.strip())


@router.get("/extension/pairing/{code}", response_model=PairingConsumeResponse)
async def consume_extension_pairing_get(request: Request, code: str) -> PairingConsumeResponse:
    """Legacy GET consume path (prefer POST /extension/pairing/consume)."""
    from app.services.extension.pairing import check_pairing_rate_limit

    if not check_pairing_rate_limit(_pairing_client_key(request)):
        raise HTTPException(status_code=429, detail="Too many pairing attempts")
    return _consume_pairing_or_404(code)


@router.get("/extension/setup-hints", response_model=ExtensionSetupHintsResponse)
async def get_extension_setup_hints(request: Request) -> ExtensionSetupHintsResponse:
    """Return whether extension auth token is configured (never exposes the token)."""
    from app.config.deploy_mode import is_webui_remote_mode
    from app.config.settings import settings

    bridge = get_extension_bridge()
    configured = bool(settings.extension_auth_token.get_secret_value())
    token_required = is_webui_remote_mode()
    cdp_discovered = bridge.has_direct_cdp_endpoint()
    relay_ready = await bridge.relay_cdp_ready()
    return ExtensionSetupHintsResponse(
        auth_token_configured=configured,
        auth_token_required=token_required,
        cdp_endpoint_discovered=cdp_discovered,
        relay_cdp_ready=relay_ready,
        access_policy_valid=bridge.is_access_policy_valid(),
    )


from app.api.extension.routes.clip_agent import (  # noqa: E402
    router as clip_agent_router,
)

router.include_router(clip_agent_router)
