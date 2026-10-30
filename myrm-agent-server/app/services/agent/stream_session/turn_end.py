"""Teardown steps of a turn that need the chat and the outcome only, not the stream session.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: background drain of compaction debt)
- app.services.copilot.run_digest_store::RunDigestStore (POS: the run digest the turn ends)
- app.services.event.app_event_bus (POS: session lifecycle events that feed outbound webhooks and push notifications)
- myrm_agent_harness.agent.context_management.tracking.task_metrics::get_task_metrics (POS: compaction debt the turn left behind)

[OUTPUT]
- schedule_compaction_drain: drain in the background when the turn left compaction debt behind
- close_run_digest: end the run digest of the chat and announce the session outcome
- publish_session_lifecycle_webhook_event: publish session_completed / session_failed

[POS]
The finalize of a request's turn (``stream_finalize``, which holds the stream session) and the end of a turn a fired
approval timer resumed (``streaming_support.hitl_timeout``, which holds none) end a turn with these same steps, so a
turn that ends by timer is announced and drained like one that ends by request.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

logger = logging.getLogger(__name__)


def schedule_compaction_drain(chat_id: str | None) -> None:
    """Drain in the background when the turn left compaction debt behind."""
    if not chat_id:
        return
    from myrm_agent_harness.agent.context_management.tracking.task_metrics import get_task_metrics

    metrics = get_task_metrics(chat_id)
    if metrics and getattr(metrics, "compaction_debt_pending", False):
        from app.services.chat.chat_service import ChatService

        logger.info("Scheduling background drain for %s due to compaction debt.", chat_id)
        ChatService.schedule_background_drain(chat_id)


def close_run_digest(
    chat_id: str,
    *,
    phase: RunDigestPhase,
    progress_steps: list[dict[str, object]],
    agent_id: str | None,
    was_cancelled: bool,
    had_fatal_error: bool,
) -> None:
    """End the run digest of the chat and announce the session outcome to the lifecycle webhooks."""
    from app.services.copilot.run_digest_store import RunDigestStore

    RunDigestStore.end_run(chat_id, phase=phase, progress_steps=progress_steps)
    publish_session_lifecycle_webhook_event(
        chat_id=chat_id,
        phase=phase,
        agent_id=agent_id,
        was_cancelled=was_cancelled,
        had_fatal_error=had_fatal_error,
    )


def publish_session_lifecycle_webhook_event(
    *,
    chat_id: str,
    phase: RunDigestPhase,
    agent_id: str | None,
    was_cancelled: bool,
    had_fatal_error: bool,
) -> None:
    """Publish session_completed / session_failed for outbound lifecycle webhooks."""
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    if phase == RunDigestPhase.COMPLETED:
        event_type = AppEventType.SESSION_COMPLETED
    else:
        event_type = AppEventType.SESSION_FAILED

    get_event_bus().publish(
        AppEvent(
            event_type=event_type,
            data={
                "chat_id": chat_id,
                "agent_id": agent_id,
                "phase": phase.value,
                "was_cancelled": was_cancelled,
                "had_fatal_error": had_fatal_error,
            },
        )
    )
