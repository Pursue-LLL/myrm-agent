"""
[INPUT]
- app.database.connection::get_session (POS: 数据库连接管理)
- app.database.models::SystemNotification (POS: persisted async notification model)

[OUTPUT]
- SystemNotificationService.create_notification: persist system notification records

[POS]
System notification persistence service for API/business layers.
Supports independent session writes and caller-session reuse.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models import SystemNotification

logger = logging.getLogger(__name__)


class SystemNotificationService:
    @staticmethod
    async def create_notification(
        title: str,
        message: str,
        type: str,
        source: str,
        meta_data: dict[str, object] | None = None,
        session: AsyncSession | None = None,
    ) -> str:
        """Create a persistent system notification."""
        notif_id = uuid.uuid4().hex
        try:
            if session is not None:
                notif = SystemNotification(
                    id=notif_id,
                    title=title,
                    message=message,
                    type=type,
                    source=source,
                    meta_data=meta_data,
                )
                session.add(notif)
                await session.flush()
                return notif_id

            async with get_session() as session:
                notif = SystemNotification(
                    id=notif_id, title=title, message=message, type=type, source=source, meta_data=meta_data
                )
                session.add(notif)
                await session.commit()
            return notif_id
        except Exception as e:
            logger.error(f"Failed to create system notification: {e}")
            return ""
