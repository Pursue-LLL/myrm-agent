"""Continual session overlay service for business-level persistence and graduation.

[INPUT]
- myrm_agent_harness.agent.continual.overlay::SessionOverlay
- app.services.skills.draft_notification::persist_skill_draft_record

[OUTPUT]
- graduate_session_overlay_to_growth: Graduate a validated in-flight overlay into a reviewable growth case.

[POS]
Business service bridging in-flight continual session overlays with the persistent skill growth pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.skills.draft_notification import persist_skill_draft_record

if TYPE_CHECKING:
    from myrm_agent_harness.api import SessionOverlay

logger = logging.getLogger(__name__)


async def graduate_session_overlay_to_growth(
    overlay: SessionOverlay,
    *,
    user_id: str,
    chat_id: str | None = None,
) -> str | None:
    """Graduate a successfully validated Continual SessionOverlay into a reviewable growth case.

    Bridges zero-reset in-flight recovery into permanent human-auditable skill evolution.
    """
    try:
        tool_name = str(overlay.patch_data.get("tool_name", "general_tool"))
        advisory = str(
            overlay.patch_data.get("advisory_instruction")
            or overlay.patch_data.get("procedural_rule")
            or overlay.trigger_reason
        )
        manifest = (
            getattr(overlay, "change_manifest", None)
            or overlay.patch_data.get("change_manifest")
        )
        payload = {
            "skill_name": f"continual_{tool_name}_guard",
            "description": f"[Continual Recovery] {advisory}",
            "patch_content": advisory,
            "trigger_condition": f"Failure or stall on tool [{tool_name}]",
            "source": "continual",
            "confidence": 0.88,
            "prediction_manifest": manifest,
            "target_layer": overlay.shell_type.value,
            "target_pathology": "unhandled_exception",
        }
        record_id = await persist_skill_draft_record(
            user_id=user_id,
            action_type=f"continual_{overlay.shell_type.value}",
            payload=payload,
            chat_id=chat_id,
            reason=f"Auto-graduated from session overlay {overlay.overlay_id}: {overlay.trigger_reason}",
        )
        logger.info(
            "Graduated session overlay %s into growth case record %s",
            overlay.overlay_id,
            record_id,
        )
        return record_id
    except Exception as e:
        logger.warning(
            "Failed to graduate session overlay %s to growth case: %s",
            overlay.overlay_id,
            e,
        )
        return None
