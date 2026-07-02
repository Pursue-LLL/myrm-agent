"""项目 API 模块"""

from fastapi import APIRouter

from .milestone_router import router as milestone_router
from .router import router as project_router

router = APIRouter()
router.include_router(project_router)
router.include_router(milestone_router)
