"""Browser Extension Bridge API endpoints.

[INPUT]
- app.services.extension.bridge::get_extension_bridge (POS: singleton bridge instance)

[OUTPUT]
- ws_router: WebSocket endpoint for extension connection (ws://.../api/ws/extension)
- router: REST endpoints for domain authorization management

[POS]
API layer for the browser extension bridge. Provides:
1. WebSocket endpoint for the extension to connect and maintain persistent connection
2. REST APIs for frontend to manage authorized domains and view connection status
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket
from pydantic import BaseModel, Field

from app.services.extension.bridge import get_extension_bridge

logger = logging.getLogger(__name__)

router = APIRouter()
ws_router = APIRouter()


# --- WebSocket Endpoint ---


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
    from app.config.settings import settings

    expected_token = settings.extension_auth_token.get_secret_value()
    if expected_token and token != expected_token:
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
    extension_version: str = ""
    browser_name: str = ""
    authorized_domains: list[str] = Field(default_factory=list)
    available_tabs: list[ExtensionTabResponse] = Field(default_factory=list)


class DomainsUpdateRequest(BaseModel):
    """Request to update authorized domains."""

    domains: list[str] = Field(
        ...,
        description="List of domain patterns to authorize (e.g., ['github.com', '*.google.com'])",
    )


class DomainsUpdateResponse(BaseModel):
    """Response after domain update."""

    authorized_domains: list[str]


@router.get("/extension/status", response_model=ExtensionStatusResponse)
async def get_extension_status() -> ExtensionStatusResponse:
    """Get current browser extension connection status."""
    bridge = get_extension_bridge()
    status = await bridge.get_status()
    return ExtensionStatusResponse(
        connected=status.connected,
        extension_version=status.extension_version,
        browser_name=status.browser_name,
        authorized_domains=status.authorized_domains,
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
    return DomainsUpdateResponse(authorized_domains=bridge.get_authorized_domains())


@router.put("/extension/domains", response_model=DomainsUpdateResponse)
async def update_authorized_domains(body: DomainsUpdateRequest) -> DomainsUpdateResponse:
    """Update the list of authorized domains for extension control.

    Only tabs on authorized domains can be controlled by the Agent.
    This is a security boundary — the user explicitly grants per-domain access.
    """
    bridge = get_extension_bridge()
    await bridge.set_authorized_domains(body.domains)
    return DomainsUpdateResponse(authorized_domains=bridge.get_authorized_domains())


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


@router.get("/extension/setup-hints", response_model=ExtensionSetupHintsResponse)
async def get_extension_setup_hints() -> ExtensionSetupHintsResponse:
    """Return whether extension auth token is configured (never exposes the token)."""
    from app.config.settings import settings

    configured = bool(settings.extension_auth_token.get_secret_value())
    return ExtensionSetupHintsResponse(auth_token_configured=configured)
