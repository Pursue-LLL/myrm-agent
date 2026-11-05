"""引导流程、Second Brain 应用与 SearXNG 启停/探测。

[POS]
配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from filelock import FileLock

from .support import (
    _SECOND_BRAIN_APPLY_LOCK,
    _acquire_second_brain_cross_process_lock,
    _release_second_brain_cross_process_lock,
    _require_local_deploy_mode,
    _second_brain_apply_lock_path,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/onboarding/complete")
async def complete_config_onboarding() -> dict[str, object]:
    """Mark user's first-time configuration as complete.

    Should be called after user successfully configures their first provider.
    """
    from app.database.connection import get_session
    from app.services.config.onboarding import complete_onboarding

    async with get_session() as db:
        success = await complete_onboarding(db, "sandbox")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to complete onboarding")

    return {"success": True, "message": "Onboarding completed successfully"}


@router.get("/onboarding/second-brain/status")
async def get_second_brain_onboarding_status(request: Request) -> dict[str, object]:
    """Return Second Brain preset checklist (agent, cron, vault, provider)."""
    from app.services.onboarding.second_brain_preset import (
        get_second_brain_preset_status,
    )

    accept_lang = request.headers.get("Accept-Language", "en")
    status = await get_second_brain_preset_status(accept_language=accept_lang)
    return status.model_dump()


@router.post("/onboarding/second-brain/apply")
async def apply_second_brain_onboarding(request: Request) -> dict[str, object]:
    """Apply Second Brain preset: user agent + read-it-later cron + checklist state."""
    from app.services.onboarding.second_brain_preset import (
        SecondBrainPresetError,
        apply_second_brain_preset,
    )

    accept_lang = request.headers.get("Accept-Language", "en")
    async with _SECOND_BRAIN_APPLY_LOCK:
        cross_process_lock = FileLock(str(_second_brain_apply_lock_path()))
        _acquire_second_brain_cross_process_lock(cross_process_lock)
        try:
            result = await apply_second_brain_preset(accept_language=accept_lang)
        except FileNotFoundError as exc:
            logger.warning("Second Brain preset file not found: %s", exc)
            raise HTTPException(status_code=500, detail="Preset file not found") from exc
        except SecondBrainPresetError as exc:
            raise HTTPException(status_code=500, detail=exc.message) from exc
        except Exception as exc:
            logger.exception("Failed to apply Second Brain preset")
            raise HTTPException(status_code=500, detail="Failed to apply Second Brain preset") from exc
        finally:
            _release_second_brain_cross_process_lock(cross_process_lock)
    return result.model_dump()

@router.post("/onboarding/searxng/start")
async def start_local_searxng_endpoint() -> dict[str, object]:
    """Start SearXNG via Docker Compose and wait until HTTP probe succeeds (local/tauri only)."""
    _require_local_deploy_mode()
    from app.services.config.searxng_setup import start_local_searxng_and_wait

    return await start_local_searxng_and_wait()


_TINY_VISION_HEALTH_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

@router.get("/onboarding/searxng/probe")
async def probe_searxng_endpoint() -> dict[str, object]:
    """Probe local search backends for zero-config setup.

    Returns:
        search: SearXNG probe results
        recommended_searxng_url: Default api_base when SearXNG is available
    """
    from app.core.channel_bridge.search_topology import get_default_searxng_api_base
    from app.services.config.onboarding import probe_local_search

    search_results = await probe_local_search()
    searxng_hit = next(
        (s for s in search_results if s.get("provider") == "searxng" and s.get("available")),
        None,
    )

    return {
        "search": search_results,
        "recommended_searxng_url": (str(searxng_hit.get("base_url")) if searxng_hit else get_default_searxng_api_base()),
    }


