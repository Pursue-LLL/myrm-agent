"""Theme workspace API router.

[INPUT]
app.api.theme.assets (POS: 主题媒体上传端点)
app.api.theme.packages (POS: 主题包导入/导出/安装端点)

[OUTPUT]
router: FastAPI APIRouter (prefix=/theme)

[POS]
聚合主题子路由 (assets + packages) 挂载到 /theme 前缀。
"""

from fastapi import APIRouter

from app.api.theme import assets, packages

router = APIRouter(prefix="/theme", tags=["theme"])

router.include_router(assets.router)
router.include_router(packages.router)
