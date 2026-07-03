"""Server hook when a harness background bash job finishes.

Appends a visible assistant message to chat history and publishes a
SYSTEM_NOTIFICATION SSE event — no headless LLM run.

[INPUT]
- myrm_agent_harness.api.hooks::BackgroundJobFinishResult
- app.services.chat.chat_service::ChatService (POS: message persistence)
- app.services.event.app_event_bus (POS: SSE bus)

[OUTPUT]
- ServerBackgroundJobFinishHandler.on_background_job_finish

[POS]
Business orchestration for harness background bash job terminal events.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from myrm_agent_harness.api.hooks import BackgroundJobFinishResult

from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


def _format_finish_message(result: BackgroundJobFinishResult) -> str:
    cmd_preview = result.command if len(result.command) <= 120 else f"{result.command[:117]}..."
    if result.status == "exited" and (result.exit_code or 0) == 0:
        return (
            f"Background task completed (pid={result.pid}).\n"
            f"Command: {cmd_preview}"
        )
    if result.error_category:
        return (
            f"Background task ended with {result.error_category} "
            f"(pid={result.pid}, status={result.status}, exit_code={result.exit_code}).\n"
            f"Command: {cmd_preview}"
        )
    return (
        f"Background task {result.status} (pid={result.pid}, exit_code={result.exit_code}).\n"
        f"Command: {cmd_preview}"
    )


class ServerBackgroundJobFinishHandler:
    """Persists background bash job completion into the chat transcript."""

    async def on_background_job_finish(self, result: BackgroundJobFinishResult) -> None:
        if not result.session_id:
            logger.warning("Background job finish ignored: missing session_id")
            return
        if result.status != "exited":
            return
        asyncio.create_task(self._process(result))

    async def _process(self, result: BackgroundJobFinishResult) -> None:
        try:
            content = _format_finish_message(result)
            message_id = f"bg_finish_{result.pid}_{int(datetime.now(tz=timezone.utc).timestamp())}"
            sent_at = datetime.now(tz=timezone.utc)

            await ChatService.append_message(
                chat_id=result.session_id,
                role="assistant",
                content=content,
                sent_at=sent_at,
                sent_timezone="UTC",
                message_id=message_id,
                extra_data={
                    "background_job": True,
                    "pid": result.pid,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "error_category": result.error_category,
                },
            )

            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.SYSTEM_NOTIFICATION,
                    data={
                        "title": "Background task finished",
                        "message": content,
                        "meta_data": {
                            "kind": "background_job_finish",
                            "chat_id": result.session_id,
                            "message_id": message_id,
                            "pid": result.pid,
                            "status": result.status,
                        },
                    },
                )
            )
            logger.info(
                "Background job finish recorded for chat=%s pid=%s status=%s",
                result.session_id,
                result.pid,
                result.status,
            )
        except Exception:
            logger.exception(
                "Failed to record background job finish chat=%s pid=%s",
                result.session_id,
                result.pid,
            )
