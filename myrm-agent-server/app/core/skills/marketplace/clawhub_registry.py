"""Persist and apply ClawHub-compatible registry mirror URL.

[INPUT]
- app.core.skills.models::UserSkillConfig.clawhub_registry_url (POS: Persisted mirror URL)
- myrm_agent_harness.agent.skills.market.sources.clawhub_registry (POS: URL SSOT + probe)

[OUTPUT]
- normalize_clawhub_registry_url: Normalize persisted mirror URL (incl. legacy migrate)
- apply_clawhub_registry_url: Apply mirror to CLAWHUB_URL and clear shadow legacy env vars
- get_registry_presets: Server-side preset catalog for Settings UI

[POS]
ClawHub registry mirror configuration. Maps user-selected Intl/CN endpoints to CLAWHUB_URL.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from myrm_agent_harness.agent.skills.market.sources.clawhub_registry import (
    CLAWHUB_CN_PRESET_URL,
    CLAWHUB_DEFAULT_URL,
    CLAWHUB_URL_ENV,
    clear_shadow_registry_env,
    migrate_legacy_registry_url,
)

logger = logging.getLogger(__name__)

# Backward re-exports for server tests and discovery probe presets.
SKILLHUB_CN_URL = CLAWHUB_CN_PRESET_URL


@dataclass(frozen=True)
class RegistryPreset:
    id: str
    url: str


def get_registry_presets() -> list[RegistryPreset]:
    return [
        RegistryPreset(id="intl", url=""),
        RegistryPreset(id="cn", url=CLAWHUB_CN_PRESET_URL),
    ]


def normalize_clawhub_registry_url(url: str | None) -> str:
    value = migrate_legacy_registry_url((url or "").strip().rstrip("/"))
    if not value or value == CLAWHUB_DEFAULT_URL:
        return ""
    return value


def apply_clawhub_registry_url(url: str | None) -> str:
    """Apply registry URL to process env and refresh in-memory ClawHub source clients."""
    normalized = normalize_clawhub_registry_url(url)
    effective = normalized or CLAWHUB_DEFAULT_URL
    os.environ[CLAWHUB_URL_ENV] = effective
    clear_shadow_registry_env()

    try:
        from .market_service import market_service

        market_service.refresh_clawhub_source()
    except Exception as exc:
        logger.warning("Failed to refresh ClawHub source after registry update: %s", exc)

    logger.info("ClawHub registry mirror set to %s", effective)
    return effective
