"""First-time configuration onboarding service.

Handles checking and marking completion of first-time user configuration.
Provides local search backend probing and the Ollama endpoint resolver.

[INPUT]
- user_id: User identifier
- Database: UserConfig table (config_key='onboarding')

[OUTPUT]
- Onboarding status (completed/not completed)
- Local search backend probe results (SearXNG)

[POS]
Business-layer onboarding service. Manages first-time user configuration flow.
Uses UserConfig with config_key='onboarding' to persist completion state.
Probes the local SearXNG endpoint for zero-config search setup.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

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
# Local endpoints
# ============================================================================

_OLLAMA_DEFAULT_URL = "http://localhost:11434"


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


async def probe_local_search() -> list[dict[str, object]]:
    """Probe local/self-hosted and free cloud search backends."""
    from myrm_agent_harness.toolkits.web_search.probe.local_probe import probe_local_search_services

    from app.core.channel_bridge.search_topology import get_searxng_probe_candidate_urls

    results = await probe_local_search_services(get_searxng_probe_candidate_urls())
    return [r.model_dump() for r in results]


__all__ = [
    "check_onboarding_status",
    "complete_onboarding",
    "get_ollama_base_url",
    "probe_local_search",
]
