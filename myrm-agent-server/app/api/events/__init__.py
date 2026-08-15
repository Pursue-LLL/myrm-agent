"""Agent Events API

实时推送（SSE 通知）与本地模式权限审批 API。
"""

from fastapi import APIRouter

from app.api.events.notifications import router as notifications_router
from app.api.events.permissions import router as permissions_router

router = APIRouter()
router.include_router(permissions_router)
router.include_router(notifications_router)

__all__ = ["router"]
