"""[INPUT]
- app.api.wiki.routes.imports.folder_zip::router (POS: Wiki 批量导入子包的一部分；由 __init__.py 聚合为单一 router。)
- app.api.wiki.routes.imports.obsidian::router (POS: Wiki 批量导入子包的一部分；由 __init__.py 聚合为单一 router。)

[OUTPUT]
- router: APIRouter that mounts the folder/zip and Obsidian import routes

[POS]
Wiki 批量导入路由聚合出口。
"""

from fastapi import APIRouter

from app.api.wiki.routes.imports.folder_zip import router as folder_zip_router
from app.api.wiki.routes.imports.obsidian import router as obsidian_router

router = APIRouter(tags=["wiki"])
router.include_router(folder_zip_router)
router.include_router(obsidian_router)
