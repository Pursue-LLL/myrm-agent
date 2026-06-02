"""Pump generated SSE chunks into the global stream buffer."""

from __future__ import annotations

import asyncio
import logging

from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.stream_session.stream_chunks import generate_cancellable_stream
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.sse_helpers import error_sse

logger = logging.getLogger(__name__)

async def pump_to_buffer(session: AgentStreamSession, buffer: object) -> None:
    try:
        async for chunk in generate_cancellable_stream(session):
            if chunk.strip():
                await buffer.append(chunk)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Error pumping stream to buffer: %s", e, exc_info=True)
        await buffer.append(error_sse(f"Stream interrupted: {e}", session.params.message_id))
    finally:
        await buffer.end_stream()

        # --- Offline Guardian Notification & Cleanup ---
        try:
            if session.is_long_running_task:
                try:
                    if session.durable_registered and session.request.chat_id:
                        from sqlalchemy import delete

                        from app.database.models.chat import OfflineDurableTask
                        from app.platform_utils import get_session_factory

                        session_factory = get_session_factory()
                        async with session_factory() as db:
                            await db.execute(
                                delete(OfflineDurableTask).where(
                                    OfflineDurableTask.chat_id == session.request.chat_id
                                )
                            )
                            await db.commit()
                            logger.info(
                                "Offline Durable Guardian task cleared: chat_id=%s",
                                session.request.chat_id,
                            )

                            from app.services.power.manager import release_power_lock

                            release_power_lock(session.request.chat_id)
                except Exception as e:
                    logger.error("Failed to clear durable task: %s", e)

            if session.is_long_running_task and not session.cancel_token.is_cancelled:
                if await session.http_request.is_disconnected():
                    from app.services.infra.system_notification import SystemNotificationService

                    await SystemNotificationService.create_notification(
                        title="Task Completed (Offline Guardian)",
                        message=(
                            "Your background task has successfully completed. "
                            "You can view the results in the chat."
                        ),
                        type="success",
                        source="offline_guardian",
                        meta_data={
                            "chat_id": session.request.chat_id,
                            "message_id": session.params.message_id,
                            "action_url": f"/{session.request.chat_id}",
                        },
                    )
                    logger.info("Offline Guardian notification sent for: %s", session.params.message_id)
        except Exception as e:
            logger.error("Offline Guardian notification error: %s", e)

        async def _delayed_remove() -> None:
            try:
                await asyncio.sleep(300)
                await session.registry.remove(session.params.message_id)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(
            _delayed_remove(),
            name=f"buffer_cleanup_{session.params.message_id}",
        )
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)


async def launch_buffered_stream(session: AgentStreamSession) -> StreamingResponse:
    buffer = await session.registry.get_or_create(session.params.message_id)
    asyncio.create_task(pump_to_buffer(session, buffer))
    return StreamingResponse(
        content=buffer.subscribe(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
