"""Integration skill availability gates for prebuilt skills (Catalog + Agent runtime).

[INPUT]
- app.services.agent.session_credential_assembler::assemble_session_credentials, XAI_ISSUER (POS: the rule a turn's credentials are assembled by)
- app.services.integrations.oauth_store::load_oauth_credentials_row, decrypt_oauth_credentials (POS: stored OAuth credentials)
- app.core.channel_bridge.config_readiness::load_readiness_inputs (POS: stored provider bundle, also before a default model exists)
- app.core.skills.gates.requirements_availability (POS: bins/env/config verdict honouring saved skill env)
- app.database.connection::get_session (POS: async DB session factory)

[OUTPUT]
- INTEGRATION_SKILL_ISSUERS / INTEGRATION_SKILL_UNAVAILABLE_REASONS: prebuilt skills with a dedicated credential rule
- ALL_INTEGRATION_GATED_SKILL_IDS: the ids that are hidden when the verdict cannot be computed
- apply_integration_oauth_availability: updates Catalog Skill entries
- apply_integration_oauth_to_metadata: mutates Agent SkillMetadata entries
- enrich_skill_metadata_integration_oauth: opens a session and applies the verdict, failing closed for dedicated ids
- IntegrationOAuthSkillBackend / wrap_integration_oauth_backend: SkillBackend wrapper applying all gates for one track

[POS]
Server business-layer guard — keeps skill availability consistent between Catalog and Agent runtime: the `requires`
verdict (bins, env, config; env includes keys saved in skill settings), then the credential verdict. A skill that
needs OAuth issuers (the ones its frontmatter declares plus its dedicated issuer) is available exactly when a turn
on the same credential track is handed a token for every one of them. The verdict runs the production assembler
over the stored credentials instead of restating its rules, so what a skill is listed for and what a turn receives
cannot drift apart. The assembler is called without a channel: a listing has no channel token to account for.
Shared by Skills HTTP API and loader.create_skill_backend().
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol, cast

from myrm_agent_harness.agent.security import CredentialTrack
from myrm_agent_harness.api import SkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills.gates.requirements_availability import (
    apply_requirements_availability_to_catalog,
    apply_requirements_availability_to_metadata,
)
from app.core.skills.models import Skill
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.agent.session_credential_assembler import XAI_ISSUER, assemble_session_credentials
from app.services.integrations.oauth_store import decrypt_oauth_credentials, load_oauth_credentials_row

logger = logging.getLogger(__name__)

GOOGLE_WORKSPACE_SKILL_ID = "google-workspace"
X_LIVE_SEARCH_SKILL_ID = "x-live-search"

GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE = "Connect Google Workspace in Settings → Integrations → Credentials"
X_LIVE_SEARCH_UNAVAILABLE = (
    "Add an xAI provider in Settings → Models & Providers, "
    "or connect your SuperGrok token in Settings → Integrations → Credentials"
)

# Prebuilt skill id → the issuer it needs whatever its frontmatter declares
INTEGRATION_SKILL_ISSUERS: dict[str, str] = {
    GOOGLE_WORKSPACE_SKILL_ID: GOOGLE_WORKSPACE_ISSUER,
    X_LIVE_SEARCH_SKILL_ID: XAI_ISSUER,
}

# Prebuilt skill id → guidance shown when its dedicated issuer has no token
INTEGRATION_SKILL_UNAVAILABLE_REASONS: dict[str, str] = {
    GOOGLE_WORKSPACE_SKILL_ID: GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    X_LIVE_SEARCH_SKILL_ID: X_LIVE_SEARCH_UNAVAILABLE,
}

ALL_INTEGRATION_GATED_SKILL_IDS = frozenset(INTEGRATION_SKILL_ISSUERS)


class _GatedSkill(Protocol):
    """What the verdict reads and writes; the catalog ``Skill`` and the runtime ``SkillMetadata`` both have it."""

    @property
    def id(self) -> str: ...

    available: bool
    unavailable_reason: str | None
    required_oauth_issuers: list[str]


def _required_issuers(skill: _GatedSkill) -> tuple[str, ...]:
    """The dedicated issuer first, then the declared ones in frontmatter order, without repeats."""
    dedicated = INTEGRATION_SKILL_ISSUERS.get(skill.id)
    return tuple(dict.fromkeys([*([dedicated] if dedicated else []), *skill.required_oauth_issuers]))


def _unavailable_reason(skill_id: str, missing_issuer: str) -> str:
    if missing_issuer == INTEGRATION_SKILL_ISSUERS.get(skill_id):
        return INTEGRATION_SKILL_UNAVAILABLE_REASONS[skill_id]
    return f"Connect {missing_issuer} in Settings → Integrations → Credentials (required by skill)"


async def _issuers_with_token(db: AsyncSession, track: CredentialTrack, *, reads_providers: bool) -> frozenset[str]:
    """Issuers a turn on ``track`` would be handed a token for, from the stored credentials.

    The provider bundle is read only when asked: loading it goes through the user config, which refreshes an
    expiring subscription token over the network, and a verdict that needs no provider must not trigger that.
    """
    row = await load_oauth_credentials_row(db)
    oauth_credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted) if row else None

    providers: dict[str, object] | None = None
    if reads_providers:
        from app.core.channel_bridge.config_readiness import load_readiness_inputs

        # A fresh install has no default model, which makes load_user_configs() refuse; the catalog must still list.
        providers, _ = await load_readiness_inputs()

    credentials = await assemble_session_credentials(
        oauth_credentials_dict=oauth_credentials,
        providers_dict=providers,
        channel=None,
        credential_track=track,
    )
    return frozenset(credential.issuer for credential in credentials if credential.token)


async def _apply_credential_verdict(skills: Sequence[_GatedSkill], db: AsyncSession, track: CredentialTrack) -> None:
    """Mark every skill unavailable whose required issuers the track is not handed a token for."""
    required = [(skill, _required_issuers(skill)) for skill in skills]
    wanted = {issuer for _, issuers in required for issuer in issuers}
    if not wanted:
        return

    held = await _issuers_with_token(db, track, reads_providers=XAI_ISSUER in wanted)
    for skill, issuers in required:
        missing = next((issuer for issuer in issuers if issuer not in held), None)
        if missing is not None:
            skill.available = False
            skill.unavailable_reason = _unavailable_reason(skill.id, missing)


async def apply_integration_oauth_availability(
    skills: list[Skill],
    db: AsyncSession,
    *,
    credential_track: CredentialTrack = CredentialTrack.PERSONAL,
) -> None:
    """Set available=False when a skill requires dependencies or credentials that are missing."""
    await apply_requirements_availability_to_catalog(skills)
    await _apply_credential_verdict(skills, db, credential_track)


async def apply_integration_oauth_to_metadata(
    skills: list[SkillMetadata],
    db: AsyncSession,
    *,
    credential_track: CredentialTrack = CredentialTrack.PERSONAL,
) -> None:
    """Apply the credential verdict to Agent runtime SkillMetadata."""
    await _apply_credential_verdict(skills, db, credential_track)


async def enrich_skill_metadata_integration_oauth(
    skills: list[SkillMetadata],
    *,
    credential_track: CredentialTrack = CredentialTrack.PERSONAL,
) -> None:
    """Apply the requirements verdict, then the credential gates (loader / backend wrapper)."""
    await apply_requirements_availability_to_metadata(skills)

    if not any(_required_issuers(meta) for meta in skills):
        return
    try:
        from app.database.connection import get_session

        async with get_session() as db:
            await apply_integration_oauth_to_metadata(skills, db, credential_track=credential_track)
    except Exception as exc:
        logger.warning("Failed to enrich skill OAuth availability: %s", exc)
        for meta in skills:
            if meta.id in ALL_INTEGRATION_GATED_SKILL_IDS:
                meta.available = False
                meta.unavailable_reason = INTEGRATION_SKILL_UNAVAILABLE_REASONS[meta.id]


class IntegrationOAuthSkillBackend:
    """SkillBackend wrapper that applies the availability gates on list/load for one credential track."""

    def __init__(self, base: SkillBackend, *, credential_track: CredentialTrack = CredentialTrack.PERSONAL) -> None:
        self._base = base
        self._credential_track = credential_track

    async def list_skills(self) -> list[SkillMetadata]:
        skills = await self._base.list_skills()
        await enrich_skill_metadata_integration_oauth(skills, credential_track=self._credential_track)
        return skills

    async def load_skills(self, skill_ids: list[str]) -> list[SkillMetadata]:
        skills = await self._base.load_skills(skill_ids)
        await enrich_skill_metadata_integration_oauth(skills, credential_track=self._credential_track)
        return skills

    async def get_skill_content(self, skill_name: str) -> str:
        return await self._base.get_skill_content(skill_name)

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        return await self._base.get_skill_resources(skill_name, path)

    async def list_skill_resources(self, skill_name: str) -> list[str]:
        return await self._base.list_skill_resources(skill_name)


def wrap_integration_oauth_backend(
    base: SkillBackend,
    *,
    credential_track: CredentialTrack = CredentialTrack.PERSONAL,
) -> SkillBackend:
    return cast(SkillBackend, IntegrationOAuthSkillBackend(base, credential_track=credential_track))
