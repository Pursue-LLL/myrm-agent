"""Auto-enable x-live-search prebuilt skill when xAI provider is configured.

[INPUT]
- app.services.agent.platform_config::resolve_xai_search_config (POS: xAI credential probe)
- app.core.skills.store.service::skills_service (POS: user prebuilt skill config)
- app.core.skills.oauth_availability::X_LIVE_SEARCH_SKILL_ID

[OUTPUT]
- maybe_enable_x_live_search_skill: enable skill unless user disabled it

[POS]
Server hook after providers config save — mirrors google_workspace_oauth_flow.maybe_enable_google_workspace_skill.
"""

from __future__ import annotations

import logging

from app.core.skills.oauth_availability import X_LIVE_SEARCH_SKILL_ID
from app.services.agent.platform_config import resolve_xai_search_config

logger = logging.getLogger(__name__)


async def maybe_enable_x_live_search_skill(
    providers_dict: dict[str, object] | None,
) -> tuple[bool, bool]:
    """Enable x-live-search when xAI provider is present unless user disabled it.

    Returns:
        (skill_auto_enabled, skill_was_user_disabled)
    """
    if resolve_xai_search_config(providers_dict) is None:
        return False, False

    from app.core.skills.store.service import skills_service

    config = await skills_service.user_config.get_config()
    if X_LIVE_SEARCH_SKILL_ID in config.disabled_prebuilt_ids:
        logger.info(
            "xAI provider configured but skill '%s' remains disabled by user choice",
            X_LIVE_SEARCH_SKILL_ID,
        )
        return False, True

    if X_LIVE_SEARCH_SKILL_ID not in config.enabled_prebuilt_ids:
        await skills_service.user_config.enable_prebuilt_skill(X_LIVE_SEARCH_SKILL_ID)
        return True, False

    return True, False
