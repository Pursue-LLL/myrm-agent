"""
[INPUT]
- app.database.models::SystemNotification (POS: 通知域模型)
- app.database.connection::get_session (POS: 数据库连接管理)
- app.core.channel_bridge::get_channel_gateway (POS: 渠道网关)
- app.api.notifications.schemas (POS: 通知请求/响应模型)

[OUTPUT]
- router: 通知 REST 路由（列表、单条/全部已读、DLQ 重试）
- cleanup_old_notifications: 过期通知清理（warmup 阶段调用）

[POS]
通知 REST 接口层。提供通知列表查询、单条/全部标记已读、DLQ 消息重试、过期通知清理。
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, func, select, update

from app.api.notifications.schemas import NotificationListResponse, SystemNotificationResponse
from app.core.channel_bridge import get_channel_gateway
from app.database.connection import get_session
from app.database.models import SystemNotification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["Notifications"])


async def cleanup_old_notifications() -> None:
    """Clean up read notifications older than 30 days.

    Called once during server warmup, not per-request.
    """
    try:
        async with get_session() as session:
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            stmt = delete(SystemNotification).where(
                SystemNotification.is_read == True,  # noqa: E712
                SystemNotification.created_at < thirty_days_ago,
            )
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount:
                logger.info("Cleaned up %d old read notifications", result.rowcount)
    except Exception as e:
        logger.error("Failed to cleanup old notifications: %s", e)


@router.get("", response_model=NotificationListResponse)
async def list_notifications(limit: int = 50, offset: int = 0) -> NotificationListResponse:
    async with get_session() as session:
        # Get total count
        total = await session.scalar(select(func.count()).select_from(SystemNotification))

        # Get unread count
        unread = await session.scalar(
            select(func.count()).select_from(SystemNotification).where(SystemNotification.is_read == False)  # noqa: E712
        )

        # Get items
        stmt = select(SystemNotification).order_by(SystemNotification.created_at.desc()).offset(offset).limit(limit)

        result = await session.execute(stmt)
        items = result.scalars().all()

        return NotificationListResponse(
            items=[
                SystemNotificationResponse(
                    id=n.id,
                    title=n.title,
                    message=n.message,
                    type=n.type,
                    source=n.source,
                    is_read=n.is_read,
                    created_at=n.created_at,
                    meta_data=n.meta_data,
                )
                for n in items
            ],
            total=total or 0,
            unread_count=unread or 0,
        )


@router.post("/read-all")
async def mark_all_as_read() -> dict[str, str]:
    async with get_session() as session:
        stmt = (
            update(SystemNotification)
            .where(
                SystemNotification.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        await session.execute(stmt)
        await session.commit()
    return {"status": "ok"}


@router.post("/{notification_id}/retry")
async def retry_notification(notification_id: str) -> dict[str, str]:
    async with get_session() as session:
        stmt = select(SystemNotification).where(SystemNotification.id == notification_id)
        result = await session.execute(stmt)
        notif = result.scalar_one_or_none()

        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found")

        if not notif.meta_data or "delivery_id" not in notif.meta_data:
            raise HTTPException(status_code=400, detail="Notification does not contain delivery_id")

        delivery_id = notif.meta_data["delivery_id"]

        gateway = get_channel_gateway()
        success = await gateway.bus.retry_dlq_message(delivery_id)

        if success:
            notif.is_read = True
            meta = dict(notif.meta_data) if notif.meta_data else {}
            meta["retried"] = True
            notif.meta_data = meta
            await session.commit()
            return {"status": "ok", "message": "Message re-enqueued successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to retry message. It may have expired or been deleted.")


@router.post("/{notification_id}/read")
async def mark_as_read(notification_id: str) -> dict[str, str]:
    async with get_session() as session:
        stmt = (
            update(SystemNotification)
            .where(
                SystemNotification.id == notification_id,
                SystemNotification.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Notification not found or already read")
    return {"status": "ok"}
