"""What becomes of a goal when a stream the server started on its own fails.

[INPUT] GoalProvider, channel_t, app_event_bus, config_loader (the owner's locale)
[OUTPUT] TriggerFailurePolicy, resolve_user_locale, publish_goal_needs_review_notification, handle_unattended_goal_stream_failure
[POS] The failure policy every unattended goal stream shares (resume, follow-up turn, wake after a background job).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider

logger = logging.getLogger(__name__)

TriggerFailurePolicy = Literal["needs_human_review", "keep_active"]


async def resolve_user_locale() -> str:
    """Load locale from personal settings (WebUI / Tauri / sandbox user config)."""
    from myrm_agent_harness.utils.locale import normalize_locale, resolve_locale

    from app.core.channel_bridge.config_loader import load_user_configs

    try:
        configs = await load_user_configs()
        ps = configs.personal_settings_dict if configs else None
        raw_locale = ps.get("locale") if ps else None
        if not raw_locale and ps:
            raw_locale = ps.get("language")
        locale_str = str(raw_locale) if raw_locale else None
        return resolve_locale(metadata_locale=locale_str, platform_locale=None, channel=None)
    except Exception:
        logger.debug("Failed to load user locale for goal stream failure", exc_info=True)
        return normalize_locale(None)


async def publish_goal_needs_review_notification(session_id: str, goal_id: str) -> None:
    """Publish goal_needs_review SSE after an unattended failure or orphan recovery."""
    from app.channels.i18n.engine import channel_t
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    locale = await resolve_user_locale()
    title = channel_t(locale, "goal_stream_failed_title")
    message = channel_t(locale, "goal_stream_failed_message")

    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={
                "title": title,
                "message": message,
                "meta_data": {
                    "kind": "goal_needs_review",
                    "chat_id": session_id,
                    "goal_id": goal_id,
                },
            },
        )
    )


async def handle_unattended_goal_stream_failure(
    session_id: str,
    goal_id: str,
    provider: GoalProvider | None,
    *,
    on_failure: TriggerFailurePolicy,
    context: str,
) -> None:
    """Apply unattended stream failure policy — review state or Cron keep-active.

    Only a goal still ACTIVE is escalated: a run that already parked, paused or finished
    the goal before failing must not have that state overwritten.
    """
    if on_failure == "keep_active":
        logger.error(
            "Goal %s remains ACTIVE for Cron fallback after %s failure",
            goal_id,
            context,
        )
        return

    if provider is None:
        logger.warning(
            "Cannot mark goal %s as NEEDS_HUMAN_REVIEW: no GoalProvider",
            goal_id,
        )
        return

    from myrm_agent_harness.agent.goals.types import GoalStatus

    try:
        goal = await provider.get_goal(goal_id)
        if goal is None or goal.status is not GoalStatus.ACTIVE:
            logger.info("Goal %s already left ACTIVE during %s; keeping its state", goal_id, context)
            return
        await provider.update_status(goal_id, GoalStatus.NEEDS_HUMAN_REVIEW)
    except Exception:
        logger.warning("Could not mark goal %s as NEEDS_HUMAN_REVIEW", goal_id)
        return

    try:
        await publish_goal_needs_review_notification(session_id, goal_id)
    except Exception:
        logger.exception(
            "Failed to publish goal_needs_review notification for goal %s",
            goal_id,
        )
