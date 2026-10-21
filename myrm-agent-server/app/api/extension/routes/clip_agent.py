"""Wiki clip agent scope REST routes for browser extension sync.

[INPUT]
- app.services.extension.clip (POS: clip target agent UserConfig SSOT)
- app.services.extension.bridge::get_extension_bridge (POS: MV3 WS push)

[OUTPUT]
- GET/PUT /extension/clip-agent

[POS]
REST layer for wiki clip agent scope between WebUI Settings and MV3 extension.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.extension.bridge import get_extension_bridge
from app.services.extension.clip import (
    get_extension_clip_agent_config,
    set_extension_clip_agent_config,
)

router = APIRouter(tags=["extension-clip"])


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
