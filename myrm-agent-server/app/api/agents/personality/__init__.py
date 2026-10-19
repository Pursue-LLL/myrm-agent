"""Communication style preset API package.

[INPUT]
- personality.catalog::router (POS: communication style catalog endpoint)

[OUTPUT]
- router: aggregated FastAPI router for the communication style catalog

[POS]
api/agents/personality 包门面：聚合沟通风格相关路由，挂载在 /agents 前缀下。
"""

from fastapi import APIRouter

from .catalog import router as catalog_router

router = APIRouter()
router.include_router(catalog_router)

__all__ = ["router"]
