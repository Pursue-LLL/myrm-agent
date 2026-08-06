"""Browser Extension Bridge API endpoints.

[INPUT]
- app.services.extension.bridge::get_extension_bridge (POS: singleton bridge instance)

[OUTPUT]
- ws_router: WebSocket endpoint for extension connection (ws://.../api/ws/extension)
- router: REST endpoints for domain authorization management

[POS]
API layer for the browser extension bridge. Provides:
1. WebSocket endpoint for the extension to connect and maintain persistent connection
2. REST APIs for frontend to manage authorized domains and view connection status,
   plus wiki clip agent scope sync for the browser extension.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Query, WebSocket
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
    extension_version: str = ""
    browser_name: str = ""
    authorized_domains: list[str] = Field(default_factory=list)
    available_tabs: list[ExtensionTabResponse] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class DomainsUpdateRequest(BaseModel):
    """Request to update authorized domains."""

    domains: list[str] = Field(
        ...,
        description="List of domain patterns to authorize (e.g., ['github.com', '*.google.com'])",
    )


class DomainPolicyWarningResponse(BaseModel):
    """Structured warning for domain authorization semantics."""

    code: Literal["wildcard_includes_root"]
    pattern: str
    root_domain: str


class DomainsUpdateResponse(BaseModel):
    """Response after domain update."""

    authorized_domains: list[str]
    warnings: list[DomainPolicyWarningResponse] = Field(default_factory=list)


def _to_warning_responses(warnings: list[DomainPolicyWarning]) -> list[DomainPolicyWarningResponse]:
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
    return ExtensionStatusResponse(
        connected=status.connected,
        handshake_ready=status.handshake_ready,
        extension_version=status.extension_version,
        browser_name=status.browser_name,
        authorized_domains=status.authorized_domains,
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
async def update_authorized_domains(body: DomainsUpdateRequest) -> DomainsUpdateResponse:
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


class ExtensionClipAgentResponse(BaseModel):
    """Wiki clip target agent synced between WebUI and MV3 extension."""

    agent_id: str | None = Field(
        default=None,
        description="Agent whose wiki vault receives browser clips",
    )
    web_ui_origin: str | None = Field(
        default=None,
        description="WebUI origin for extension deep links (e.g. duplicate review)",
    )


class ExtensionClipAgentUpdateRequest(BaseModel):
    """Update wiki clip agent scope for the browser extension."""

    agent_id: str | None = Field(
        default=None,
        description="Agent whose wiki vault receives browser clips",
    )
    web_ui_origin: str | None = Field(
        default=None,
        description="WebUI origin for extension deep links",
    )


@router.get("/extension/clip-agent", response_model=ExtensionClipAgentResponse)
async def get_extension_clip_agent() -> ExtensionClipAgentResponse:
    """Return wiki clip agent scope stored in UserConfig (extension sync SSOT)."""
    from app.services.extension.clip_agent_config import get_extension_clip_agent_config

    cfg = await get_extension_clip_agent_config()
    return ExtensionClipAgentResponse(
        agent_id=cfg.agent_id,
        web_ui_origin=cfg.web_ui_origin,
    )


@router.put("/extension/clip-agent", response_model=ExtensionClipAgentResponse)
async def update_extension_clip_agent(
    body: ExtensionClipAgentUpdateRequest,
) -> ExtensionClipAgentResponse:
    """Persist wiki clip agent scope and push to connected extension."""
    from app.services.extension.clip_agent_config import set_extension_clip_agent_config

    cfg = await set_extension_clip_agent_config(
        agent_id=body.agent_id,
        web_ui_origin=body.web_ui_origin,
    )
    bridge = get_extension_bridge()
    await bridge.notify_clip_agent_config(cfg.agent_id, cfg.web_ui_origin)
    return ExtensionClipAgentResponse(
        agent_id=cfg.agent_id,
        web_ui_origin=cfg.web_ui_origin,
    )


@router.get("/extension/setup-hints", response_model=ExtensionSetupHintsResponse)
async def get_extension_setup_hints() -> ExtensionSetupHintsResponse:
    """Return whether extension auth token is configured (never exposes the token)."""
    from app.config.deploy_mode import is_webui_remote_mode
    from app.config.settings import settings

    bridge = get_extension_bridge()
    configured = bool(settings.extension_auth_token.get_secret_value())
    token_required = is_webui_remote_mode()
    cdp_discovered = bridge.has_direct_cdp_endpoint()
    return ExtensionSetupHintsResponse(
        auth_token_configured=configured,
        auth_token_required=token_required,
        cdp_endpoint_discovered=cdp_discovered,
    )
