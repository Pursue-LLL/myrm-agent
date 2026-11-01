"""First-time configuration onboarding service.

Handles checking and marking completion of first-time user configuration.
Provides local model auto-detection.

[INPUT]
- user_id: User identifier
- Database: UserConfig table (config_key='onboarding')

[OUTPUT]
- Onboarding status (completed/not completed)
- Local model probe results (Ollama, LM Studio)

[POS]
Business-layer onboarding service. Manages first-time user configuration flow.
Uses UserConfig with config_key='onboarding' to persist completion state.
Probes local model endpoints (Ollama, LM Studio) for zero-config experience.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_ONBOARDING_CONFIG_KEY = "onboarding"


async def check_onboarding_status(db: "AsyncSession", user_id: str) -> bool:
    """Check if user has completed first-time configuration.

    Looks for a UserConfig record with config_key='onboarding' that contains
    a non-null 'completed_at' value.
    """
    from sqlalchemy import select

    from app.database.models import UserConfig

    result = await db.execute(
        select(UserConfig.config_value).where(
            UserConfig.config_key == _ONBOARDING_CONFIG_KEY,
        )
    )
    config_value = result.scalar_one_or_none()

    if config_value is None:
        return False

    return bool(config_value.get("completed_at"))


async def complete_onboarding(db: "AsyncSession", user_id: str) -> bool:
    """Mark user's first-time configuration as complete.

    Creates or updates a UserConfig record with config_key='onboarding'.
    """
    from sqlalchemy import select

    from app.database.models import UserConfig

    result = await db.execute(
        select(UserConfig).where(
            UserConfig.config_key == _ONBOARDING_CONFIG_KEY,
        )
    )
    existing = result.scalar_one_or_none()

    now_iso = datetime.now(timezone.utc).isoformat()

    if existing:
        if existing.config_value.get("completed_at"):
            logger.debug("User %s already completed onboarding", user_id)
            return True
        existing.config_value = {**existing.config_value, "completed_at": now_iso}
        existing.version = f"{int(datetime.now(timezone.utc).timestamp() * 1000)}_0"
    else:
        record = UserConfig(
            id=str(uuid.uuid4()),
            config_key=_ONBOARDING_CONFIG_KEY,
            config_value={"completed_at": now_iso},
            version=f"{int(datetime.now(timezone.utc).timestamp() * 1000)}_0",
            last_device_id="server",
        )
        db.add(record)

    await db.commit()
    logger.info("User %s completed first-time configuration", user_id)
    return True


# ============================================================================
# Local model auto-detection
# ============================================================================

_OLLAMA_DEFAULT_URL = "http://localhost:11434"
_LM_STUDIO_DEFAULT_URL = "http://localhost:1234"
_PROBE_TIMEOUT_S = 3.0


def get_ollama_base_url() -> str:
    """Resolve Ollama base URL with environment override and protocol normalization.

    Supports OLLAMA_BASE_URL, OLLAMA_HOST, and OLLAMA_HOST_URL.
    Automatically prepends 'http://' if protocol is missing, and strips trailing slashes.
    """
    raw = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_HOST_URL") or "").strip()
    if raw:
        if not raw.startswith("http://") and not raw.startswith("https://"):
            raw = f"http://{raw}"
        return raw.rstrip("/")
    return _OLLAMA_DEFAULT_URL


class DetectedModel(BaseModel):
    """A model discovered on a local endpoint."""

    name: str
    size_bytes: int | None = None
    modified_at: str | None = None


class LocalProbeResult(BaseModel):
    """Result of probing a local model service."""

    provider: str
    base_url: str
    available: bool
    models: list[DetectedModel] = []
    error: str | None = None
    latency_ms: int = 0


async def _probe_ollama(base_url: str | None = None) -> LocalProbeResult:
    """Probe Ollama service at the given base URL."""
    import time

    resolved_base_url = (base_url or get_ollama_base_url()).rstrip("/")
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            resp = await client.get(f"{resolved_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()

        elapsed = int((time.monotonic() - start) * 1000)
        raw_models: list[dict[str, object]] = data.get("models", [])
        models = [
            DetectedModel(
                name=str(m.get("name", "")),
                size_bytes=int(m["size"]) if "size" in m else None,
                modified_at=str(m.get("modified_at", "")),
            )
            for m in raw_models
            if m.get("name")
        ]
        return LocalProbeResult(
            provider="ollama",
            base_url=resolved_base_url,
            available=True,
            models=models,
            latency_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return LocalProbeResult(
            provider="ollama",
            base_url=resolved_base_url,
            available=False,
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=elapsed,
        )


async def _probe_lm_studio(base_url: str = _LM_STUDIO_DEFAULT_URL) -> LocalProbeResult:
    """Probe LM Studio service at the given base URL."""
    import time

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            resp = await client.get(f"{base_url}/v1/models")
            resp.raise_for_status()
            data = resp.json()

        elapsed = int((time.monotonic() - start) * 1000)
        raw_models: list[dict[str, object]] = data.get("data", [])
        models = [DetectedModel(name=str(m.get("id", ""))) for m in raw_models if m.get("id")]
        return LocalProbeResult(
            provider="lm_studio",
            base_url=base_url,
            available=True,
            models=models,
            latency_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return LocalProbeResult(
            provider="lm_studio",
            base_url=base_url,
            available=False,
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=elapsed,
        )


async def probe_local_models() -> list[LocalProbeResult]:
    """Probe all known local model services concurrently.

    Checks Ollama and LM Studio endpoints. Returns results for each
    regardless of whether they're available, so the frontend can display
    appropriate guidance.
    """
    import asyncio

    results = await asyncio.gather(
        _probe_ollama(),
        _probe_lm_studio(),
        return_exceptions=True,
    )

    probe_results: list[LocalProbeResult] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            provider = "ollama" if i == 0 else "lm_studio"
            base_url = get_ollama_base_url() if i == 0 else _LM_STUDIO_DEFAULT_URL
            logger.warning("Probe %s failed unexpectedly: %s", provider, result)
            probe_results.append(
                LocalProbeResult(
                    provider=provider,
                    base_url=base_url,
                    available=False,
                    error=str(result),
                )
            )
        else:
            probe_results.append(result)

    available = [r for r in probe_results if r.available]
    if available:
        total_models = sum(len(r.models) for r in available)
        logger.info(
            "Local model probe: %d service(s) available, %d model(s) found",
            len(available),
            total_models,
        )
    else:
        logger.info("Local model probe: no local services detected")

    return probe_results


async def probe_local_search() -> list[dict[str, object]]:
    """Probe local/self-hosted and free cloud search backends."""
    from myrm_agent_harness.toolkits.web_search.probe.local_probe import probe_local_search_services

    from app.core.channel_bridge.search_topology import get_searxng_probe_candidate_urls

    results = await probe_local_search_services(get_searxng_probe_candidate_urls())
    return [r.model_dump() for r in results]


__all__ = [
    "DetectedModel",
    "LocalProbeResult",
    "check_onboarding_status",
    "complete_onboarding",
    "probe_local_models",
    "probe_local_search",
]
