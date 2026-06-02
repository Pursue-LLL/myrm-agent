"""项目 API 模块"""

from fastapi import APIRouter

from .router import router as project_router

router = APIRouter()
router.include_router(project_router)
