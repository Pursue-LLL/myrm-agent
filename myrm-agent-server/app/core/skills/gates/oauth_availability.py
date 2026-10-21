"""Integration skill availability gates for prebuilt skills (Catalog + Agent runtime).

[INPUT]
- app.services.integrations.oauth_store::is_oauth_issuer_connected (POS: OAuth credential persistence)
- app.core.channel_bridge.config_loader::load_user_configs (POS: user config loader with TTL cache)
- app.services.agent.platform_config::resolve_xai_search_config (POS: xAI provider key resolver)
- app.core.skills.gates.requirements_availability (POS: bins/env/config verdict honouring saved skill env)
- app.database.connection::get_session (POS: async DB session factory)
- app.services.agent.session_credential_assembler::XAI_ISSUER (POS: canonical issuer key for xAI)

[OUTPUT]
- INTEGRATION_SKILL_ISSUERS: OAuth-gated prebuilt skills
- apply_integration_oauth_availability: updates Catalog Skill entries
- apply_integration_oauth_to_metadata: mutates Agent SkillMetadata entries
- IntegrationOAuthSkillBackend / wrap_integration_oauth_backend: SkillBackend wrapper applying all gates

[POS]
Server business-layer guard — keeps skill availability consistent between Catalog and Agent runtime: `requires`
verdict (bins, env, config; env includes keys saved in skill settings), then OAuth-issuer / xAI-provider gates
that mark integration-backed skills unavailable when credentials are missing. Shared by Skills HTTP API
and loader.create_skill_backend().
"""

from __future__ import annotations

import logging
from typing import cast

from myrm_agent_harness.api import SkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills.gates.requirements_availability import (
    apply_requirements_availability_to_catalog,
    apply_requirements_availability_to_metadata,
)
from app.core.skills.models import Skill
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import is_oauth_issuer_connected

logger = logging.getLogger(__name__)

GOOGLE_WORKSPACE_SKILL_ID = "google-workspace"
X_LIVE_SEARCH_SKILL_ID = "x-live-search"

GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE = "Connect Google Workspace in Settings → Integrations → Credentials"
X_LIVE_SEARCH_UNAVAILABLE = (
    "Add an xAI provider in Settings → Models & Providers, "
    "or connect your SuperGrok token in Settings → Integrations → Credentials"
)

# Prebuilt skill id → oauthCredentials issuer key
INTEGRATION_SKILL_ISSUERS: dict[str, str] = {
    GOOGLE_WORKSPACE_SKILL_ID: GOOGLE_WORKSPACE_ISSUER,
}

# Prebuilt skill id → unavailable reason when the provider gate fails
INTEGRATION_SKILL_UNAVAILABLE_REASONS: dict[str, str] = {
    GOOGLE_WORKSPACE_SKILL_ID: GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    X_LIVE_SEARCH_SKILL_ID: X_LIVE_SEARCH_UNAVAILABLE,
}

ALL_INTEGRATION_GATED_SKILL_IDS = set(INTEGRATION_SKILL_ISSUERS) | {X_LIVE_SEARCH_SKILL_ID}


def _metadata_skill_id(meta: SkillMetadata) -> str:
    return meta.storage_skill_id or meta.name


async def _issuer_connected_map(db: AsyncSession, skill_ids: set[str]) -> dict[str, bool]:
    issuers = {skill_id: issuer for skill_id, issuer in INTEGRATION_SKILL_ISSUERS.items() if skill_id in skill_ids}
    if not issuers:
        return {}

    unique_issuers = set(issuers.values())
    issuer_connected = {issuer: await is_oauth_issuer_connected(db, issuer) for issuer in unique_issuers}
    return {skill_id: issuer_connected[issuer] for skill_id, issuer in issuers.items()}


async def _is_xai_provider_configured() -> bool:
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.platform_config import resolve_xai_search_config

    configs = await load_user_configs()
    if resolve_xai_search_config(configs.providers_dict) is not None:
        return True

    from app.database.connection import get_session
    from app.services.agent.session_credential_assembler import XAI_ISSUER

    try:
        async with get_session() as db:
            return await is_oauth_issuer_connected(db, XAI_ISSUER)
    except Exception:
        return False


async def _integration_skill_connected_map(skill_ids: set[str]) -> dict[str, bool]:
    if X_LIVE_SEARCH_SKILL_ID not in skill_ids:
        return {}
    return {X_LIVE_SEARCH_SKILL_ID: await _is_xai_provider_configured()}


def _unavailable_reason(skill_id: str) -> str:
    return INTEGRATION_SKILL_UNAVAILABLE_REASONS.get(
        skill_id,
        GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    )


async def apply_integration_oauth_availability(
    skills: list[Skill],
    db: AsyncSession,
) -> None:
    """Set available=False when a skill requires dependencies or credentials that are missing."""
    await apply_requirements_availability_to_catalog(skills)

    has_custom_issuers = any(bool(getattr(s, "required_oauth_issuers", None)) for s in skills)
    relevant_ids = {skill.id for skill in skills if skill.id in ALL_INTEGRATION_GATED_SKILL_IDS}
    if not relevant_ids and not has_custom_issuers:
        return

    oauth_connected = await _issuer_connected_map(db, relevant_ids)
    other_connected = await _integration_skill_connected_map(relevant_ids)
    issuer_status_cache: dict[str, bool] = {}

    for skill in skills:
        if skill.id in ALL_INTEGRATION_GATED_SKILL_IDS:
            is_connected = oauth_connected.get(skill.id, other_connected.get(skill.id, True))
            if not is_connected:
                skill.available = False
                skill.unavailable_reason = _unavailable_reason(skill.id)
                continue

        # Frontmatter declarative required_oauth_issuers dynamic preflight check
        req_issuers = getattr(skill, "required_oauth_issuers", None) or []
        if req_issuers:
            for req_issuer in req_issuers:
                if req_issuer not in issuer_status_cache:
                    issuer_status_cache[req_issuer] = await is_oauth_issuer_connected(db, req_issuer)
                if not issuer_status_cache[req_issuer]:
                    skill.available = False
                    skill.unavailable_reason = (
                        f"Connect {req_issuer} in Settings → Integrations → Credentials (required by skill)"
                    )
                    break


async def apply_integration_oauth_to_metadata(
    skills: list[SkillMetadata],
    db: AsyncSession,
) -> None:
    """Apply the OAuth-issuer and provider gates to Agent runtime SkillMetadata."""
    has_custom_issuers = any(bool(getattr(m, "required_oauth_issuers", None)) for m in skills)
    relevant_ids = {_metadata_skill_id(meta) for meta in skills if _metadata_skill_id(meta) in ALL_INTEGRATION_GATED_SKILL_IDS}
    if not relevant_ids and not has_custom_issuers:
        return

    oauth_connected = await _issuer_connected_map(db, relevant_ids)
    other_connected = await _integration_skill_connected_map(relevant_ids)
    issuer_status_cache: dict[str, bool] = {}

    for meta in skills:
        skill_id = _metadata_skill_id(meta)
        if skill_id in ALL_INTEGRATION_GATED_SKILL_IDS:
            is_connected = oauth_connected.get(skill_id, other_connected.get(skill_id, True))
            if not is_connected:
                meta.available = False
                meta.unavailable_reason = _unavailable_reason(skill_id)
                continue

        # Frontmatter declarative required_oauth_issuers dynamic preflight check
        req_issuers = getattr(meta, "required_oauth_issuers", None) or []
        if req_issuers:
            for req_issuer in req_issuers:
                if req_issuer not in issuer_status_cache:
                    issuer_status_cache[req_issuer] = await is_oauth_issuer_connected(db, req_issuer)
                if not issuer_status_cache[req_issuer]:
                    meta.available = False
                    meta.unavailable_reason = f"Connect {req_issuer} in Settings → Integrations → Credentials (required by skill)"
                    break


async def enrich_skill_metadata_integration_oauth(skills: list[SkillMetadata]) -> None:
    """Apply the requirements verdict, then the credential gates (loader / backend wrapper)."""
    await apply_requirements_availability_to_metadata(skills)

    has_gated_id = any(_metadata_skill_id(meta) in ALL_INTEGRATION_GATED_SKILL_IDS for meta in skills)
    has_custom_issuers = any(bool(getattr(meta, "required_oauth_issuers", None)) for meta in skills)
    if not has_gated_id and not has_custom_issuers:
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
    """SkillBackend wrapper that applies the availability gates on list/load."""

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
