"""Web Push event dispatcher — subscribes to ServerEventBus and broadcasts push notifications.

Runs in parallel with NotificationDispatcher (IM) and BtwTaskNotifier.
Only pushes events that are meaningful for offline/background notification
scenarios (approvals, goal completions, health alerts, etc.).

[INPUT]
- app.services.event.app_event_bus::ServerEventBus, AppEvent, AppEventType
- app.core.web_push.push_deep_links::resolve_push_url
- app.core.web_push.service::get_web_push_service

[OUTPUT]
- WebPushDispatcher: start()/stop() lifecycle

[POS]
Independent ServerEventBus subscriber. Does NOT modify dispatcher.py or btw_notifier.py.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus

logger = logging.getLogger(__name__)

_PUSH_TEMPLATES: dict[AppEventType, tuple[str, str]] = {
    AppEventType.APPROVAL_REQUIRED: (
        "Approval Required",
        "{action_type} (severity: {severity}) — tap to review",
    ),
    AppEventType.HEALTH_ALERT: (
        "Health Alert",
        "{component}: {message}",
    ),
    AppEventType.BUDGET_ALERT: (
        "Budget Alert",
        "{status} — {pct}% used (${today_cost} / ${daily_limit})",
    ),
    AppEventType.GOAL_TERMINAL: (
        "Goal {status}",
        "{objective}",
    ),
    AppEventType.CHANNEL_DISCONNECTED: (
        "Channel Disconnected",
        "Channel '{channel}' went offline",
    ),
    AppEventType.SYSTEM_NOTIFICATION: (
        "{title}",
        "{message}",
    ),
    AppEventType.OAUTH_REAUTH_REQUIRED: (
        "Authorization Expired",
        "{issuer}: {reason} — re-authorize in Settings",
    ),
}

_BACKGROUND_TASK_TITLES: dict[str, str] = {
    "completed": "Task Completed",
    "failed": "Task Failed",
    "blocked": "Task Blocked",
    "pending_review": "Task Pending Review",
    "rejected": "Task Rejected",
}


def _background_task_title(status: str) -> str:
    """Notification title for a kanban BACKGROUND_TASK_DONE status."""
    return _BACKGROUND_TASK_TITLES.get(status, "Task Update")


class WebPushDispatcher:
    """Subscribes to ServerEventBus and pushes relevant events via Web Push."""

    def __init__(self, event_bus: ServerEventBus) -> None:
        self._bus = event_bus
        self._queue: asyncio.Queue[AppEvent] | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._queue = self._bus.subscribe()
        self._task = asyncio.create_task(self._dispatch_loop(), name="web-push-dispatcher")
        logger.info("WebPushDispatcher started")

    async def stop(self) -> None:
        if self._queue:
            try:
                self._bus.unsubscribe(self._queue)
            except Exception as exc:
                logger.warning("Failed to unsubscribe WebPushDispatcher: %s", exc)
            self._queue = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("WebPushDispatcher task error during stop: %s", exc)
            self._task = None
        logger.info("WebPushDispatcher stopped")

    async def _dispatch_loop(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            try:
                await self._handle_event(event)
            except Exception as exc:
                logger.warning(
                    "WebPushDispatcher: failed to handle %s: %s",
                    event.event_type,
                    exc,
                )

    async def _handle_event(self, event: AppEvent) -> None:
        if event.data.get("suppress_web_push") is True:
            return

        if event.event_type == AppEventType.BACKGROUND_TASK_DONE:
            await self._push_background_task_done(event)
            return

        template = _PUSH_TEMPLATES.get(event.event_type)
        if not template:
            return

        title_tpl, body_tpl = template
        try:
            title = title_tpl.format(**event.data)
            body = body_tpl.format(**event.data)
        except (KeyError, ValueError) as exc:
            logger.debug(
                "Skipping Web Push for %s: template format error: %s",
                event.event_type,
                exc,
            )
            return

        await self._broadcast(event, title, body)

    async def _push_background_task_done(self, event: AppEvent) -> None:
        """Push a kanban task outcome with a status-aware title.

        Covers completed/failed/blocked/pending_review/rejected so the user is
        never told "Task Completed" for a failed, blocked, or review-pending
        task. The caller has already honored ``suppress_web_push``.
        """
        title = _background_task_title(str(event.data.get("status", "")))
        body = str(event.data.get("title", "")) or "background task"
        await self._broadcast(event, title, body)

    async def _broadcast(
        self,
        event: AppEvent,
        title: str,
        body: str,
    ) -> None:
        from app.core.web_push.push_deep_links import resolve_push_url
        from app.core.web_push.service import get_web_push_service

        service = get_web_push_service()
        await service.broadcast(title=title, body=body, url=resolve_push_url(event))
