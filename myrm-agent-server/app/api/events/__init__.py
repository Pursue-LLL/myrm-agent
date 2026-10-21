"""Agent Events API

实时推送（SSE 通知）API。
"""

from fastapi import APIRouter

from app.api.events.notifications import router as notifications_router

router = APIRouter()
router.include_router(notifications_router)

__all__ = ["router"]
