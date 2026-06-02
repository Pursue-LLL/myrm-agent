from datetime import datetime

from pydantic import BaseModel


class SystemNotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    type: str
    source: str
    is_read: bool
    created_at: datetime
    meta_data: dict[str, object] | None = None


class NotificationListResponse(BaseModel):
    items: list[SystemNotificationResponse]
    total: int
    unread_count: int
