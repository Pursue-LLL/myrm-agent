"""Wiki 批量导入路由聚合出口。

[OUTPUT]
router: 依次挂载 folder/zip 与 obsidian/obsidian-zip，保持原注册顺序。
"""

from fastapi import APIRouter

from app.api.wiki.routes.imports.folder_zip import router as folder_zip_router
from app.api.wiki.routes.imports.obsidian import router as obsidian_router

router = APIRouter(tags=["wiki"])
router.include_router(folder_zip_router)
router.include_router(obsidian_router)
