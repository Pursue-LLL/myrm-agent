"""General Agent package."""

from fastapi import APIRouter

from .active_sessions import router as active_sessions_router
from .phase_response import router as phase_response_router
from .media_config import router as media_config_router
from .streaming import router as streaming_router

router = APIRouter()
router.include_router(streaming_router)
router.include_router(phase_response_router)
router.include_router(media_config_router)
router.include_router(active_sessions_router)
