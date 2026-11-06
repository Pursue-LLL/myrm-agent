"""[INPUT]
- app.schemas.config::OMNI_CONFIG_MODELS (POS: 配置 API 数据模型)
- app.api.config.routes.support::_VALID_CONFIG_KEYS / _readiness_db_timeout_sec (POS: 配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。)

[OUTPUT]
- get_config_schema: 获取指定配置项的 JSON Schema
- get_config_readiness: Check configuration readiness status.

[POS]
配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.schemas.config import (
    OMNI_CONFIG_MODELS,
)

from .support import _VALID_CONFIG_KEYS, _readiness_db_timeout_sec

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/schema/{key}", response_model=dict)
async def get_config_schema(key: str) -> dict[str, object]:
    """获取指定配置项的 JSON Schema"""
    if key not in _VALID_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid config key: {key}")

    model = OMNI_CONFIG_MODELS.get(key)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"Schema not found for config key: {key}. This config has not been migrated to Omni-Config yet.",
        )

    return model.model_json_schema()


@router.get("/readiness", response_model=dict)
async def get_config_readiness() -> dict[str, object]:
    """Check configuration readiness status.

    Returns configuration completeness status for each config type
    (provider, search, mcp, etc.) to help frontend guide user setup.

    Example response:
    {
        "provider": {
            "is_ready": false,
            "missing_items": ["api_key"],
            "suggestions": ["Add API key in Settings > Model Service"]
        },
        "search": {"is_ready": true},
        "onboarding_completed": false
    }
    """
    from app.core.channel_bridge.config_readiness import (
        ProviderConfigChecker,
        SearchConfigChecker,
        load_readiness_inputs,
    )
    from app.database.connection import get_session
    from app.services.config.onboarding import check_onboarding_status

    try:
        providers_dict, search_configured = await asyncio.wait_for(
            load_readiness_inputs(),
            timeout=_readiness_db_timeout_sec(),
        )
    except TimeoutError:
        logger.warning(
            "Readiness config load timed out after %.1fs; returning degraded snapshot",
            _readiness_db_timeout_sec(),
        )
        return {
            "provider": {
                "is_ready": False,
                "missing_items": ["config_load_timeout"],
                "suggestions": ["Backend is busy; retry shortly"],
            },
            "search": {
                "is_ready": False,
                "missing_items": ["config_load_timeout"],
                "suggestions": ["Backend is busy; retry shortly"],
            },
            "onboarding_completed": True,
            "degraded": True,
        }
    except Exception as exc:
        logger.warning("Failed to load user configs for readiness check: %s", exc)
        return {
            "provider": {
                "is_ready": False,
                "missing_items": ["config_load_failed"],
                "suggestions": ["Please try again or contact support"],
            },
            "search": {
                "is_ready": False,
                "missing_items": ["config_load_failed"],
                "suggestions": ["Please try again or contact support"],
            },
            "onboarding_completed": True,
            "degraded": True,
        }

    provider_checker = ProviderConfigChecker()
    provider_result = provider_checker.check(providers_dict)

    search_checker = SearchConfigChecker()
    if search_configured:
        search_result = search_checker.check({"searchServiceConfigs": [{"enabled": True}]})
    else:
        search_result = search_checker.check(None)

    onboarding_completed = True
    degraded = False
    try:

        async def _load_onboarding_completed() -> bool:
            async with get_session() as db:
                return await check_onboarding_status(db, "sandbox")

        onboarding_completed = await asyncio.wait_for(
            _load_onboarding_completed(),
            timeout=_readiness_db_timeout_sec(),
        )
    except TimeoutError:
        logger.warning(
            "Readiness onboarding check timed out after %.1fs; assuming completed to avoid shell stall",
            _readiness_db_timeout_sec(),
        )
        onboarding_completed = True
        degraded = True
    except Exception as exc:
        logger.warning("Readiness onboarding check failed: %s", exc)
        degraded = True

    return {
        "provider": provider_result.to_dict(),
        "search": search_result.to_dict(),
        "onboarding_completed": onboarding_completed,
        "degraded": degraded,
    }
