"""[INPUT]
- app.api.wiki.routes.imports.folder_zip::folder_zip_router (POS: Wiki 批量导入子包的一部分；由 __init__.py 聚合为单一 router。)
- app.api.wiki.routes.imports.obsidian::obsidian_router (POS: Wiki 批量导入子包的一部分；由 __init__.py 聚合为单一 router。)

[OUTPUT]
- APIRouter
- folder_zip_router
- obsidian_router

[POS]
Wiki 批量导入路由聚合出口。
"""

from fastapi import APIRouter

from app.api.wiki.routes.imports.folder_zip import router as folder_zip_router
from app.api.wiki.routes.imports.obsidian import router as obsidian_router

router = APIRouter(tags=["wiki"])
router.include_router(folder_zip_router)
router.include_router(obsidian_router)
