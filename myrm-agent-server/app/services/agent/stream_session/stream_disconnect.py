"""PWA disconnect tolerance and offline guardian registration."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select

from app.database.models.chat import OfflineDurableTask
from app.platform_utils import get_session_factory
from app.services.agent.stream_session.stream_session_types import (
    GRACE_PERIOD_SECONDS,
    AgentStreamSession,
)
from app.services.power.manager import acquire_power_lock

logger = logging.getLogger(__name__)


def build_disconnect_checker(session: AgentStreamSession) -> Callable[[], Awaitable[bool]]:
    async def _check() -> bool:
        # If multiplexed, we don't rely on the HTTP request connection state
        if getattr(session.request, "multiplexed", False):
            return False
            
        disconnected = await session.http_request.is_disconnected()
        has_active_subscribers = session.collector.has_subscribers

        if not disconnected or has_active_subscribers:
            session.disconnect_time = None
            return False

        if session.is_long_running_task:
            if not session.durable_registered and session.request.chat_id:
                try:
                    session_factory = get_session_factory()
                    async with session_factory() as db:
                        exists = await db.execute(
                            select(OfflineDurableTask).where(OfflineDurableTask.chat_id == session.request.chat_id)
                        )
                        if not exists.scalars().first():
                            task = OfflineDurableTask(
                                id=str(uuid.uuid4()),
                                chat_id=session.request.chat_id,
                                action_mode=session.request.action_mode,
                                serialized_params=session.params.model_dump(mode="json"),
                            )
                            db.add(task)
                            await db.commit()
                            logger.info(
                                "Offline Durable Guardian activated: chat_id=%s",
                                session.request.chat_id,
                            )
                            acquire_power_lock(session.request.chat_id)
                except Exception as e:
                    logger.error("Failed to register durable task: %s", e)
                session.durable_registered = True
            logger.debug("Offline Guardian took over task: %s", session.params.message_id)
            return False

        if session.disconnect_time is None:
            session.disconnect_time = time.time()
            logger.info(
                "PWA Disconnect Tolerance: Starting %ss grace period for message %s",
                GRACE_PERIOD_SECONDS,
                session.params.message_id,
            )
            return False

        elapsed = time.time() - session.disconnect_time
        if elapsed < GRACE_PERIOD_SECONDS:
            return False

        logger.warning(
            "PWA Disconnect Tolerance: Grace period expired (%ss), cancelling message %s",
            GRACE_PERIOD_SECONDS,
            session.params.message_id,
        )
        return True

    return _check
