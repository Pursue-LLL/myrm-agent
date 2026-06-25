"""Integration OAuth availability for prebuilt skills (Catalog + Agent runtime).

[INPUT]
- app.services.integrations.oauth_store::is_oauth_issuer_connected (POS: oauthCredentials probe)
- app.core.skills.models::Skill (POS: Catalog API skill entries)
- myrm_agent_harness.backends.skills.types::SkillMetadata (POS: Agent runtime skill metadata)

[OUTPUT]
- INTEGRATION_SKILL_ISSUERS: prebuilt skill id → OAuth issuer map
- apply_integration_oauth_availability: mutates Catalog Skill entries
- apply_integration_oauth_to_metadata: mutates Agent SkillMetadata entries
- IntegrationOAuthSkillBackend: SkillBackend wrapper for runtime enrichment

[POS]
Server business-layer guard — marks integration-backed prebuilt skills unavailable when OAuth
is disconnected. Shared by Skills HTTP API and loader.create_skill_backend().
"""

from __future__ import annotations

import logging
from typing import cast

from myrm_agent_harness.backends.skills.protocols import SkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills.models import Skill
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import is_oauth_issuer_connected

logger = logging.getLogger(__name__)

GOOGLE_WORKSPACE_SKILL_ID = "google-workspace"
GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE = (
    "Connect Google Workspace in Settings → Integrations → Credentials"
)

# Prebuilt skill id → oauthCredentials issuer key
INTEGRATION_SKILL_ISSUERS: dict[str, str] = {
    GOOGLE_WORKSPACE_SKILL_ID: GOOGLE_WORKSPACE_ISSUER,
}


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


async def apply_integration_oauth_availability(
    skills: list[Skill],
    db: AsyncSession,
) -> None:
    """Set available=False when a prebuilt skill requires OAuth that is not connected."""
    relevant_ids = {skill.id for skill in skills if skill.id in INTEGRATION_SKILL_ISSUERS}
    if not relevant_ids:
        return

    connected = await _issuer_connected_map(db, relevant_ids)
    for skill in skills:
        if skill.id not in INTEGRATION_SKILL_ISSUERS:
            continue
        if connected.get(skill.id, False):
            continue
        skill.available = False
        skill.unavailable_reason = GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


async def apply_integration_oauth_to_metadata(
    skills: list[SkillMetadata],
    db: AsyncSession,
) -> None:
    """Apply the same OAuth availability rules to Agent runtime SkillMetadata."""
    relevant_ids = {_metadata_skill_id(meta) for meta in skills if _metadata_skill_id(meta) in INTEGRATION_SKILL_ISSUERS}
    if not relevant_ids:
        return

    connected = await _issuer_connected_map(db, relevant_ids)
    for meta in skills:
        skill_id = _metadata_skill_id(meta)
        if skill_id not in INTEGRATION_SKILL_ISSUERS:
            continue
        if connected.get(skill_id, False):
            continue
        meta.available = False
        meta.unavailable_reason = GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


async def enrich_skill_metadata_integration_oauth(skills: list[SkillMetadata]) -> None:
    """Load DB session and enrich SkillMetadata list (loader / backend wrapper)."""
    if not any(_metadata_skill_id(meta) in INTEGRATION_SKILL_ISSUERS for meta in skills):
        return
    try:
        from app.database.connection import get_session

        async with get_session() as db:
            await apply_integration_oauth_to_metadata(skills, db)
    except Exception as exc:
        logger.warning("Failed to enrich skill OAuth availability: %s", exc)
        for meta in skills:
            skill_id = _metadata_skill_id(meta)
            if skill_id in INTEGRATION_SKILL_ISSUERS:
                meta.available = False
                meta.unavailable_reason = GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


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
