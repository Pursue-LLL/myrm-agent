"""Agent Events API

仅本地模式启用的事件查询与实时推送 API。
"""

from fastapi import APIRouter

from app.api.events.notifications import router as notifications_router
from app.api.events.permissions import router as permissions_router
from app.api.events.router import router as events_router

router = APIRouter()
router.include_router(events_router)
router.include_router(permissions_router)
router.include_router(notifications_router)

__all__ = ["router"]
