"""Turns the notices the cron engine raises into the app events the WebUI, voice session and push channels consume.

[INPUT]
- myrm_agent_harness.toolkits.cron::CronNotice, CronNoticeKind (POS: one user-facing fact about a job)
- app.channels.i18n.engine::channel_t (POS: wording in the user's language)
- app.core.channel_bridge.locale_provider::resolve_user_locale (POS: the user's language preference)
- app.services.event.app_event_bus::AppEvent, AppEventType, get_event_bus (POS: SSE / web push / IM fan-out)

[OUTPUT]
- publish_cron_notice: the scheduler's notice callback; publishes CRON_UPDATED and a localized SYSTEM_NOTIFICATION

[POS]
The one place that decides how a cron notice looks to the user: severity, title and message per notice kind.
The engine reports facts only. Run outcomes keep the ``voice_background_task_done`` kind so a duplex voice
session announces them in the chat the job is bound to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from myrm_agent_harness.toolkits.cron import CronNotice, CronNoticeKind

from app.channels.i18n.engine import channel_t
from app.core.channel_bridge.locale_provider import resolve_user_locale
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

_Level = Literal["success", "warning", "error"]

_RUN_EVENT_KIND: Final = "voice_background_task_done"
_PAUSE_EVENT_KIND: Final = "cron_job_paused"
_SOURCE: Final = "cron_reminder"


@dataclass(frozen=True, slots=True)
class _Presentation:
    """How one notice kind reads: its severity, event kind and catalog keys."""

    level: _Level
    event_kind: str
    title_key: str
    # None: the engine's own text (a run's output or error snippet) is the message.
    message_key: str | None = None


_PRESENTATION: Final[dict[CronNoticeKind, _Presentation]] = {
    CronNoticeKind.RUN_SUCCEEDED: _Presentation("success", _RUN_EVENT_KIND, "cron_notice_title"),
    CronNoticeKind.RUN_FAILED: _Presentation("error", _RUN_EVENT_KIND, "cron_notice_failed_title"),
    CronNoticeKind.JOB_EXPIRED: _Presentation(
        "warning", _PAUSE_EVENT_KIND, "cron_notice_paused_title", "cron_notice_expired_message"
    ),
    CronNoticeKind.JOB_MAX_FIRES_REACHED: _Presentation(
        "warning", _PAUSE_EVENT_KIND, "cron_notice_paused_title", "cron_notice_max_fires_message"
    ),
}


async def publish_cron_notice(notice: CronNotice) -> None:
    """Publish one notice: ``CRON_UPDATED`` refreshes cron views, ``SYSTEM_NOTIFICATION`` is what the user reads."""
    presentation = _PRESENTATION[notice.kind]
    locale = await resolve_user_locale()
    title = str(channel_t(locale, presentation.title_key, job_name=notice.job_name))
    message = (
        notice.text
        if presentation.message_key is None
        else str(channel_t(locale, presentation.message_key, max_fires=notice.max_fires))
    )

    bus = get_event_bus()
    bus.publish(
        AppEvent(
            event_type=AppEventType.CRON_UPDATED,
            data={
                "kind": notice.kind,
                "level": presentation.level,
                "job_name": notice.job_name,
                "chat_id": notice.chat_id,
            },
        )
    )
    bus.publish(
        AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={
                "title": title,
                "message": message,
                "meta_data": {
                    "kind": presentation.event_kind,
                    "level": presentation.level,
                    "chat_id": notice.chat_id or "",
                    "source": _SOURCE,
                },
            },
        )
    )
