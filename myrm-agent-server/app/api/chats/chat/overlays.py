"""Session overlays query and manual rollback API endpoints.

[INPUT]
- session_id: str (Chat / Session identifier)
- overlay_id: str (SessionOverlay identifier)

[OUTPUT]
- GET /{session_id}/overlays: List[ActiveOverlayResponse]
- POST /{session_id}/overlays/{overlay_id}/rollback: Status result

[POS]
Exposes in-memory session overlays and rollback capabilities to the WebUI.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

router = APIRouter()


class ActiveOverlayResponse(BaseModel):
    """Schema representing an active session overlay for WebUI rendering."""

    overlayId: str = Field(..., description="Overlay unique identifier")
    shellType: Literal["prompt_patch", "skill_variant", "subagent_config", "procedural_memory"] = Field(
        ..., description="Four-shell classification type"
    )
    triggerReason: str = Field(..., description="Failure signature or trigger reason")
    remainingTurns: int = Field(..., description="Remaining TTL turns before graceful auto-expiration")
    advisoryText: str = Field("", description="Optional advisory instruction for the UI")


@router.get("/{session_id}/overlays", response_model=StandardSuccessResponse)
async def get_session_overlays(session_id: str) -> StandardSuccessResponse:
    """Retrieve active session overlays for a given session."""
    try:
        from myrm_agent_harness.agent.session_overlay.manager import (
            get_session_overlay_manager,
        )

        mgr = get_session_overlay_manager(session_id)
        active = mgr.get_active_overlays()

        target_shell_map = {
            "prompt_patch": "prompt_patch",
            "temp_skill_variant": "skill_variant",
            "subagent_config_overlay": "subagent_config",
            "procedural_memory": "procedural_memory",
        }

        results: list[dict[str, object]] = []
        for ovl in active:
            shell = target_shell_map.get(ovl.target_type.value, "skill_variant")
            results.append(
                {
                    "overlayId": ovl.overlay_id,
                    "shellType": shell,
                    "triggerReason": ovl.failure_signature or ovl.target_name,
                    "remainingTurns": ovl.ttl_turns,
                    "advisoryText": str(ovl.patch_payload.get("advisory_instruction") or ""),
                }
            )
        return success_response(results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query session overlays: {e}") from e


@router.post("/{session_id}/overlays/{overlay_id}/rollback", response_model=StandardSuccessResponse)
async def rollback_session_overlay(session_id: str, overlay_id: str) -> StandardSuccessResponse:
    """Manually rollback an active session overlay."""
    try:
        from myrm_agent_harness.agent.session_overlay.manager import (
            get_session_overlay_manager,
        )

        mgr = get_session_overlay_manager(session_id)
        success = mgr.rollback_overlay(overlay_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Overlay {overlay_id} not found or not active in session {session_id}",
            )
        return success_response({"rolled_back": True, "overlay_id": overlay_id})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rollback overlay: {e}") from e
