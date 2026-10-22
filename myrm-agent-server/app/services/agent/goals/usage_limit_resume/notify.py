"""User notification for a goal parked on, resumed from, or stopped by a provider usage limit.

[INPUT]
- app.services.agent.goals.goal_stream_trigger::resolve_user_locale (POS: personal-settings locale)
- app.channels.i18n.engine::channel_t (POS: localized notification copy)
- app.services.event.app_event_bus (POS: SYSTEM_NOTIFICATION fan-out to WebUI/Tauri)

[OUTPUT]
- GOAL_USAGE_LIMIT_KIND: ``meta_data.kind`` the frontend keys its goal refresh on
- UsageLimitNotice: wait | resumed | paused
- publish_goal_usage_limit_notification

[POS]
One notification per state change of a usage-limit hold. Copy carries no times or provider
detail; the Goal panel shows the exact resume time in the user's timezone.
"""

from __future__ import annotations

from typing import Literal

from app.channels.i18n.engine import channel_t
from app.services.agent.goals.goal_stream_trigger import resolve_user_locale
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

GOAL_USAGE_LIMIT_KIND = "goal_usage_limit"

UsageLimitNotice = Literal["wait", "resumed", "paused"]

_COPY_KEYS: dict[UsageLimitNotice, tuple[str, str]] = {
    "wait": ("goal_usage_limit_wait_title", "goal_usage_limit_wait_message"),
    "resumed": ("goal_usage_limit_resumed_title", "goal_usage_limit_resumed_message"),
    "paused": ("goal_usage_limit_paused_title", "goal_usage_limit_paused_message"),
}


async def publish_goal_usage_limit_notification(session_id: str, goal_id: str, notice: UsageLimitNotice) -> None:
    locale = await resolve_user_locale()
    title_key, message_key = _COPY_KEYS[notice]
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={
                "title": channel_t(locale, title_key),
                "message": channel_t(locale, message_key),
                "meta_data": {
                    "kind": GOAL_USAGE_LIMIT_KIND,
                    "state": notice,
                    "chat_id": session_id,
                    "goal_id": goal_id,
                },
            },
        )
    )
