import logging
import uuid

from app.database.connection import get_session
from app.database.models import SystemNotification

logger = logging.getLogger(__name__)


class SystemNotificationService:
    @staticmethod
    async def create_notification(
        title: str, message: str, type: str, source: str, meta_data: dict[str, object] | None = None
    ) -> str:
        """Create a persistent system notification."""
        notif_id = uuid.uuid4().hex
        try:
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
