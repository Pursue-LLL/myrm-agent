"""Turns the notices the cron engine raises into the app events the WebUI, voice session and push channels consume.

[INPUT]
- myrm_agent_harness.toolkits.cron::CronNotice, CronNoticeKind (POS: one user-facing fact about a job)
- myrm_agent_harness.toolkits.cron::HEARTBEAT_JOB_NAME (POS: Heartbeat — convenience layer over CronManager for periodic agent self-checks, and the one place that says which job names are reserved for the application's own jobs.)
- app.channels.i18n.engine::channel_t (POS: wording in the user's language)
- app.core.channel_bridge.locale_provider::resolve_user_locale (POS: the user's language preference)
- app.services.event.app_event_bus::AppEvent, AppEventType, get_event_bus (POS: SSE / web push / IM fan-out)

[OUTPUT]
- publish_cron_notice: the scheduler's notice callback; publishes CRON_UPDATED and a localized SYSTEM_NOTIFICATION

[POS]
The one place that decides how a cron notice looks to the user: severity, title and message per notice kind, and
the name the job goes by. The engine reports facts only. Run outcomes keep the ``voice_background_task_done`` kind
so a duplex voice session announces them in the chat the job is bound to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from myrm_agent_harness.toolkits.cron import HEARTBEAT_JOB_NAME, CronNotice, CronNoticeKind

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
    # None: the engine's snippet of the run (its output or error), led by the job's name, is the message.
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
    CronNoticeKind.JOB_PAUSED_BY_FAILURE: _Presentation(
        "warning", _PAUSE_EVENT_KIND, "cron_notice_paused_title", "cron_notice_failure_message"
    ),
}

# A system job's stored name is reserved and the user never chose it, so the user is told the job by this catalog name.
_SYSTEM_JOB_NAME_KEYS: Final = {HEARTBEAT_JOB_NAME: "cron_system_job_heartbeat"}


def _display_name(locale: str, job_name: str) -> str:
    key = _SYSTEM_JOB_NAME_KEYS.get(job_name)
    return job_name if key is None else str(channel_t(locale, key))


async def publish_cron_notice(notice: CronNotice) -> None:
    """Publish one notice: ``CRON_UPDATED`` refreshes cron views, ``SYSTEM_NOTIFICATION`` is what the user reads."""
    presentation = _PRESENTATION[notice.kind]
    locale = await resolve_user_locale()
    job_name = _display_name(locale, notice.job_name)
    title = str(channel_t(locale, presentation.title_key, job_name=job_name))
    message = (
        f"[{job_name}] {notice.text}"
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
