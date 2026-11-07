"""[INPUT]
- app.schemas.config::OMNI_CONFIG_MODELS / ConfigKey (POS: 配置 API 数据模型)

[OUTPUT]
- _readiness_db_timeout_sec: Parallel E2E sqlite contention — 2.5s causes perpetual config_load_timeout.
- _second_brain_apply_lock_path: _second_brain_apply_lock_path
- _acquire_second_brain_cross_process_lock: _acquire_second_brain_cross_process_lock
- _release_second_brain_cross_process_lock: _release_second_brain_cross_process_lock
- _validate_config_value: _validate_config_value
- _require_local_deploy_mode: _require_local_deploy_mode
- _hot_reload_cloud_browser: Hot-reload the browser pool's remote endpoint after cloud browser config changes.
- _hot_reload_browser_proxy: Hot-reload the browser pool's proxy pool after browser proxy config changes.

[POS]
配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import get_args

from fastapi import APIRouter, HTTPException
from filelock import FileLock, Timeout
from pydantic import ValidationError

from app.schemas.config import (
    OMNI_CONFIG_MODELS,
    ConfigKey,
)

logger = logging.getLogger(__name__)

_READINESS_DB_TIMEOUT_DEFAULT_SEC = 2.5
_READINESS_DB_TIMEOUT_DEV_SEC = 15.0

router = APIRouter()


def _readiness_db_timeout_sec() -> float:
    """Parallel E2E sqlite contention — 2.5s causes perpetual config_load_timeout."""
    import os

    override = os.environ.get("MYRM_READINESS_DB_TIMEOUT_SEC", "").strip()
    if override:
        try:
            return max(_READINESS_DB_TIMEOUT_DEFAULT_SEC, float(override))
        except ValueError:
            pass
    from app.server.runtime_dev_info import get_runtime_dev_info

    if get_runtime_dev_info()["dev_mode"] == "split_dev":
        return _READINESS_DB_TIMEOUT_DEV_SEC
    return _READINESS_DB_TIMEOUT_DEFAULT_SEC


router = APIRouter()

_VALID_CONFIG_KEYS: frozenset[str] = frozenset(get_args(ConfigKey))


_SECOND_BRAIN_APPLY_LOCK = asyncio.Lock()
_SECOND_BRAIN_CROSS_PROCESS_LOCK_TIMEOUT_SEC = 0.0
_SECOND_BRAIN_ONBOARDING_IN_PROGRESS_CODE = "SECOND_BRAIN_ONBOARDING_IN_PROGRESS"
_SECOND_BRAIN_ONBOARDING_IN_PROGRESS_MESSAGE = "Second Brain preset apply is already in progress. Please retry shortly."


def _second_brain_apply_lock_path() -> Path:
    from app.config.settings import settings

    lock_dir = Path(settings.database.state_dir) / "locks" / "onboarding"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "second-brain-preset.lock"


def _acquire_second_brain_cross_process_lock(lock: FileLock) -> None:
    try:
        lock.acquire(timeout=_SECOND_BRAIN_CROSS_PROCESS_LOCK_TIMEOUT_SEC)
    except Timeout as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": _SECOND_BRAIN_ONBOARDING_IN_PROGRESS_CODE,
                "message": _SECOND_BRAIN_ONBOARDING_IN_PROGRESS_MESSAGE,
            },
        ) from exc


def _release_second_brain_cross_process_lock(lock: FileLock) -> None:
    if lock.is_locked:
        lock.release()


def _validate_config_value(config_key: str, value: dict[str, object], *, operation: str) -> dict[str, object]:
    model_class = OMNI_CONFIG_MODELS.get(config_key)
    if not model_class:
        return value

    if config_key == "searchServices" and isinstance(value, dict):
        raw_configs = value.get("searchServiceConfigs")
        if isinstance(raw_configs, list):
            from app.core.integrations.search_catalog.migration import (
                migrate_search_service_configs,
            )

            dict_rows = [row for row in raw_configs if isinstance(row, dict)]
            value = {
                **value,
                "searchServiceConfigs": migrate_search_service_configs(dict_rows),
            }

    try:
        validated_data = model_class.model_validate(value)
    except ValidationError as exc:
        logger.warning("Omni-Config %s validation failed for %s: %s", operation, config_key, exc)
        field_errors = [{"field": ".".join(str(s) for s in err["loc"]), "message": err["msg"]} for err in exc.errors()]
        raise HTTPException(
            status_code=422,
            detail={"message": "Configuration validation failed", "errors": field_errors},
        ) from exc
    except Exception as exc:
        logger.warning("Omni-Config %s validation failed for %s: %s", operation, config_key, exc)
        raise HTTPException(
            status_code=422,
            detail="Configuration validation failed",
        ) from exc
    return validated_data.model_dump(exclude_unset=False)

def _require_local_deploy_mode() -> None:
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SearXNG setup is only available in local deploy mode",
        )


async def _hot_reload_cloud_browser(value: dict[str, object]) -> None:
    """Hot-reload the browser pool's remote endpoint after cloud browser config changes."""
    try:
        from app.config.browser import get_configured_browser_pool
        from app.schemas.config import BrowserCloudProviderConfigValue

        config = BrowserCloudProviderConfigValue.model_validate(value)
        endpoint = config.resolve_ws_endpoint()
        pool = get_configured_browser_pool()
        await pool.update_remote_endpoint(endpoint)
    except Exception:
        logger.debug("Hot-reload cloud browser endpoint failed (non-critical)", exc_info=True)


async def _hot_reload_browser_proxy(value: dict[str, object]) -> None:
    """Hot-reload the browser pool's proxy pool after browser proxy config changes."""
    try:
        from myrm_agent_harness.toolkits.browser.pool.proxy import RoundRobinProxyPool

        from app.config.browser import get_configured_browser_pool
        from app.schemas.config import BrowserProxyConfigValue

        config = BrowserProxyConfigValue.model_validate(value)
        proxy_pool = None
        if config.enabled and config.proxies:
            proxy_pool = RoundRobinProxyPool.from_urls(config.proxies)
        pool = get_configured_browser_pool()
        await pool.update_proxy_pool(proxy_pool)
    except Exception:
        logger.debug("Hot-reload browser proxy failed (non-critical)", exc_info=True)
