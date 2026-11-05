"""配置管理 API 组合根。

[POS]
只负责按原路径顺序挂载 routes/ 下的域路由与 pricing/privacy-preview 子路由。
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.config.pricing import pricing_router
from app.api.config.privacy_preview import privacy_preview_router
from app.api.config.routes import catalog, crud, diagnostics, media_health, onboarding
from app.api.config.routes.support import _VALID_CONFIG_KEYS
from app.schemas.config import AllConfigsResponse
from app.services.config.service import config_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=AllConfigsResponse)
async def get_all_configs(
    keys: str | None = Query(None, description="按需加载，逗号分隔的配置键，如 providers,chatSettings"),
) -> AllConfigsResponse:
    """获取配置（可按 keys 过滤）。"""
    try:
        key_list: list[str] | None = None
        if keys:
            key_list = [k.strip() for k in keys.split(",") if k.strip()]
            invalid = [k for k in key_list if k not in _VALID_CONFIG_KEYS]
            if invalid:
                raise HTTPException(status_code=400, detail=f"Invalid config keys: {invalid}")

        all_configs = await config_service.get_all(keys=key_list)
        return AllConfigsResponse(configs=all_configs)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get configs: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get configs") from e


router.include_router(catalog.router)
router.include_router(onboarding.router)
router.include_router(media_health.router)
router.include_router(pricing_router)
router.include_router(privacy_preview_router)
router.include_router(crud.router)
router.include_router(diagnostics.router)
