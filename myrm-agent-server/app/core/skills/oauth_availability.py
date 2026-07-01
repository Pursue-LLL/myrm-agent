"""Integration skill availability gates for prebuilt skills (Catalog + Agent runtime).

[INPUT]
- app.services.integrations.oauth_store::is_oauth_issuer_connected
- app.core.channel_bridge.config_loader::load_user_configs
- app.services.agent.platform_config::resolve_xai_search_config
- app.core.skills.store.user_config::UserSkillConfigManager

[OUTPUT]
- INTEGRATION_SKILL_ISSUERS: OAuth-gated prebuilt skills
- INTEGRATION_SKILL_ENV_VARS: env-var-gated prebuilt skills
- INTEGRATION_SKILL_BINS: CLI binary-gated prebuilt skills (server PATH via shutil.which)
- apply_integration_oauth_availability: mutates Catalog Skill entries
- apply_integration_oauth_to_metadata: mutates Agent SkillMetadata entries

[POS]
Server business-layer guard — marks integration-backed prebuilt skills unavailable when
required credentials, env vars, or CLI binaries are missing. Shared by Skills HTTP API
and loader.create_skill_backend().
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import cast

from myrm_agent_harness.api import SkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.storage.factory import get_storage_provider
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills.models import Skill
from app.core.skills.store.user_config import UserSkillConfigManager
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import is_oauth_issuer_connected

logger = logging.getLogger(__name__)

GOOGLE_WORKSPACE_SKILL_ID = "google-workspace"
X_LIVE_SEARCH_SKILL_ID = "x-live-search"
NOTION_WORKSPACE_SKILL_ID = "notion-workspace"
LINEAR_PROJECT_SKILL_ID = "linear-project"
XURL_SKILL_ID = "xurl"

GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE = (
    "Connect Google Workspace in Settings → Integrations → Credentials"
)
X_LIVE_SEARCH_UNAVAILABLE = "Add an xAI provider in Settings → Models & Providers"
NOTION_ENV_UNAVAILABLE = "Configure NOTION_API_KEY in skill environment settings"
LINEAR_ENV_UNAVAILABLE = "Configure LINEAR_API_KEY in skill environment settings"
XURL_BIN_UNAVAILABLE = "Install the xurl CLI and ensure it is on PATH"

# Prebuilt skill id → oauthCredentials issuer key
INTEGRATION_SKILL_ISSUERS: dict[str, str] = {
    GOOGLE_WORKSPACE_SKILL_ID: GOOGLE_WORKSPACE_ISSUER,
}

# Prebuilt skill id → required environment variable
INTEGRATION_SKILL_ENV_VARS: dict[str, str] = {
    NOTION_WORKSPACE_SKILL_ID: "NOTION_API_KEY",
    LINEAR_PROJECT_SKILL_ID: "LINEAR_API_KEY",
}

# Prebuilt skill id → required CLI binaries on PATH (SKILL.md requires.bins)
INTEGRATION_SKILL_BINS: dict[str, tuple[str, ...]] = {
    XURL_SKILL_ID: ("xurl",),
}

# Prebuilt skill id → unavailable reason when provider/env gate fails
INTEGRATION_SKILL_UNAVAILABLE_REASONS: dict[str, str] = {
    GOOGLE_WORKSPACE_SKILL_ID: GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    X_LIVE_SEARCH_SKILL_ID: X_LIVE_SEARCH_UNAVAILABLE,
    NOTION_WORKSPACE_SKILL_ID: NOTION_ENV_UNAVAILABLE,
    LINEAR_PROJECT_SKILL_ID: LINEAR_ENV_UNAVAILABLE,
    XURL_SKILL_ID: XURL_BIN_UNAVAILABLE,
}

ALL_INTEGRATION_GATED_SKILL_IDS = (
    set(INTEGRATION_SKILL_ISSUERS)
    | set(INTEGRATION_SKILL_ENV_VARS)
    | set(INTEGRATION_SKILL_BINS)
    | {X_LIVE_SEARCH_SKILL_ID}
)


def _metadata_skill_id(meta: SkillMetadata) -> str:
    return meta.storage_skill_id or meta.name


async def _issuer_connected_map(db: AsyncSession, skill_ids: set[str]) -> dict[str, bool]:
    issuers = {
        skill_id: issuer
        for skill_id, issuer in INTEGRATION_SKILL_ISSUERS.items()
        if skill_id in skill_ids
    }
    if not issuers:
        return {}

    unique_issuers = set(issuers.values())
    issuer_connected = {issuer: await is_oauth_issuer_connected(db, issuer) for issuer in unique_issuers}
    return {skill_id: issuer_connected[issuer] for skill_id, issuer in issuers.items()}


async def _is_xai_provider_configured() -> bool:
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.platform_config import resolve_xai_search_config

    configs = await load_user_configs()
    return resolve_xai_search_config(configs.providers_dict) is not None


def _are_skill_bins_available(skill_id: str) -> bool:
    required_bins = INTEGRATION_SKILL_BINS.get(skill_id)
    if not required_bins:
        return True
    return all(shutil.which(bin_name) is not None for bin_name in required_bins)


async def _is_skill_env_configured(skill_id: str, env_key: str) -> bool:
    if os.environ.get(env_key, "").strip():
        return True
    try:
        storage = get_storage_provider()
        config = await UserSkillConfigManager(storage).get_config()
        skill_env = config.skill_env_vars.get(skill_id, {})
        return bool(str(skill_env.get(env_key, "")).strip())
    except Exception as exc:
        logger.debug("Failed to read skill env for %s: %s", skill_id, exc)
        return False


async def _integration_skill_connected_map(skill_ids: set[str]) -> dict[str, bool]:
    connected: dict[str, bool] = {}
    if X_LIVE_SEARCH_SKILL_ID in skill_ids:
        connected[X_LIVE_SEARCH_SKILL_ID] = await _is_xai_provider_configured()
    for skill_id, env_key in INTEGRATION_SKILL_ENV_VARS.items():
        if skill_id in skill_ids:
            connected[skill_id] = await _is_skill_env_configured(skill_id, env_key)
    for skill_id in INTEGRATION_SKILL_BINS:
        if skill_id in skill_ids:
            connected[skill_id] = _are_skill_bins_available(skill_id)
    return connected


def _unavailable_reason(skill_id: str) -> str:
    return INTEGRATION_SKILL_UNAVAILABLE_REASONS.get(
        skill_id,
        GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    )


async def apply_integration_oauth_availability(
    skills: list[Skill],
    db: AsyncSession,
) -> None:
    """Set available=False when a prebuilt skill requires credentials that are missing."""
    relevant_ids = {skill.id for skill in skills if skill.id in ALL_INTEGRATION_GATED_SKILL_IDS}
    if not relevant_ids:
        return

    oauth_connected = await _issuer_connected_map(db, relevant_ids)
    other_connected = await _integration_skill_connected_map(relevant_ids)

    for skill in skills:
        if skill.id not in ALL_INTEGRATION_GATED_SKILL_IDS:
            continue
        is_connected = oauth_connected.get(skill.id, other_connected.get(skill.id, True))
        if is_connected:
            continue
        skill.available = False
        skill.unavailable_reason = _unavailable_reason(skill.id)


async def apply_integration_oauth_to_metadata(
    skills: list[SkillMetadata],
    db: AsyncSession,
) -> None:
    """Apply the same integration availability rules to Agent runtime SkillMetadata."""
    relevant_ids = {
        _metadata_skill_id(meta) for meta in skills if _metadata_skill_id(meta) in ALL_INTEGRATION_GATED_SKILL_IDS
    }
    if not relevant_ids:
        return

    oauth_connected = await _issuer_connected_map(db, relevant_ids)
    other_connected = await _integration_skill_connected_map(relevant_ids)

    for meta in skills:
        skill_id = _metadata_skill_id(meta)
        if skill_id not in ALL_INTEGRATION_GATED_SKILL_IDS:
            continue
        is_connected = oauth_connected.get(skill_id, other_connected.get(skill_id, True))
        if is_connected:
            continue
        meta.available = False
        meta.unavailable_reason = _unavailable_reason(skill_id)


async def enrich_skill_metadata_integration_oauth(skills: list[SkillMetadata]) -> None:
    """Load DB session and enrich SkillMetadata list (loader / backend wrapper)."""
    if not any(_metadata_skill_id(meta) in ALL_INTEGRATION_GATED_SKILL_IDS for meta in skills):
        return
    try:
        from app.database.connection import get_session

        async with get_session() as db:
            await apply_integration_oauth_to_metadata(skills, db)
    except Exception as exc:
        logger.warning("Failed to enrich skill OAuth availability: %s", exc)
        for meta in skills:
            skill_id = _metadata_skill_id(meta)
            if skill_id in ALL_INTEGRATION_GATED_SKILL_IDS:
                meta.available = False
                meta.unavailable_reason = _unavailable_reason(skill_id)


class IntegrationOAuthSkillBackend:
    """SkillBackend wrapper that applies integration OAuth availability on list/load."""

    def __init__(self, base: SkillBackend) -> None:
        self._base = base

    async def list_skills(self) -> list[SkillMetadata]:
        skills = await self._base.list_skills()
        await enrich_skill_metadata_integration_oauth(skills)
        return skills

    async def load_skills(self, skill_ids: list[str]) -> list[SkillMetadata]:
        skills = await self._base.load_skills(skill_ids)
        await enrich_skill_metadata_integration_oauth(skills)
        return skills

    async def get_skill_content(self, skill_name: str) -> str:
        return await self._base.get_skill_content(skill_name)

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        return await self._base.get_skill_resources(skill_name, path)

    async def list_skill_resources(self, skill_name: str) -> list[str]:
        return await self._base.list_skill_resources(skill_name)


def wrap_integration_oauth_backend(base: SkillBackend) -> SkillBackend:
    return cast(SkillBackend, IntegrationOAuthSkillBackend(base))
