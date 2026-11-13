"""Availability gates of the credential-needing skills: dedicated ids, declared issuers, the wrapper and its failure mode.

The credentials a test needs are stored in the shared in-memory install (``credentials``) and read back by the production
gate; the matrix of credential states, shipped skills and tracks is ``test_credential_contract``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security import CredentialTrack
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillTrust

from app.core.skills.gates.oauth_availability import (
    GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    GOOGLE_WORKSPACE_SKILL_ID,
    IntegrationOAuthSkillBackend,
    apply_integration_oauth_availability,
    apply_integration_oauth_to_metadata,
    enrich_skill_metadata_integration_oauth,
    wrap_integration_oauth_backend,
)
from app.core.skills.models import Skill
from app.core.storage.types import SkillType
from tests.support.skill_credential_store import CredentialState, CredentialStore

_TRACKS = [CredentialTrack.PERSONAL, CredentialTrack.SHARED]
_CONNECT_ISSUER = "Connect {issuer} in Settings → Integrations → Credentials (required by skill)"


def _google_workspace_skill() -> Skill:
    return Skill(
        id=GOOGLE_WORKSPACE_SKILL_ID,
        type=SkillType.PREBUILT,
        name="Google Workspace",
        description="Calendar, Gmail, Drive",
        storage_path="skills/prebuilt/google-workspace",
    )


def _google_workspace_metadata() -> SkillMetadata:
    return SkillMetadata(
        name=GOOGLE_WORKSPACE_SKILL_ID,
        description="Calendar, Gmail, Drive",
        storage_skill_id=GOOGLE_WORKSPACE_SKILL_ID,
        storage_path="skills/prebuilt/google-workspace",
        trust=SkillTrust.TRUSTED,
    )


def _skill_declaring(issuers: list[str]) -> Skill:
    return Skill(
        id="meeting-minutes-extractor",
        type=SkillType.PREBUILT,
        name="Meeting Minutes Extractor",
        description="Sync meeting notes",
        storage_path="skills/prebuilt/meeting-minutes-extractor",
        required_oauth_issuers=issuers,
    )


def _verdict(connected: bool) -> tuple[bool, str | None]:
    return (True, None) if connected else (False, GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE)


@pytest.mark.asyncio
@pytest.mark.parametrize("connected", [False, True])
async def test_the_catalog_gates_google_workspace_by_its_id_whatever_it_declares(
    credentials: CredentialStore, connected: bool
) -> None:
    await credentials.seed(CredentialState(google=connected))
    skill = _google_workspace_skill()

    async with credentials.sessions() as db:
        await apply_integration_oauth_availability([skill], db)

    assert (skill.available, skill.unavailable_reason) == _verdict(connected)


@pytest.mark.asyncio
@pytest.mark.parametrize("connected", [False, True])
async def test_the_runtime_gates_google_workspace_by_its_id_whatever_it_declares(
    credentials: CredentialStore, connected: bool
) -> None:
    await credentials.seed(CredentialState(google=connected))
    meta = _google_workspace_metadata()

    async with credentials.sessions() as db:
        await apply_integration_oauth_to_metadata([meta], db)

    assert (meta.available, meta.unavailable_reason) == _verdict(connected)


@pytest.mark.asyncio
async def test_a_skill_that_needs_no_credential_is_left_alone_and_nothing_is_read() -> None:
    other = Skill(
        id="daily-briefing",
        type=SkillType.PREBUILT,
        name="Daily Briefing",
        description="Morning briefing",
        storage_path="skills/prebuilt/daily-briefing",
    )
    db = AsyncMock()

    await apply_integration_oauth_availability([other], db)

    assert other.available is True
    db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("connected", [False, True])
async def test_a_skill_is_gated_by_the_issuers_it_declares(credentials: CredentialStore, connected: bool) -> None:
    await credentials.seed(CredentialState(google=connected))
    skill = _skill_declaring(["google_workspace"])

    async with credentials.sessions() as db:
        await apply_integration_oauth_availability([skill], db)

    assert (skill.available, skill.unavailable_reason) == (
        (True, None) if connected else (False, _CONNECT_ISSUER.format(issuer="google_workspace"))
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("connected", [False, True])
async def test_enriching_reads_the_stored_credentials_through_its_own_session(
    credentials: CredentialStore, connected: bool
) -> None:
    await credentials.seed(CredentialState(google=connected))
    meta = _google_workspace_metadata()

    await enrich_skill_metadata_integration_oauth([meta])

    assert (meta.available, meta.unavailable_reason) == _verdict(connected)


@pytest.mark.asyncio
async def test_enriching_hides_a_dedicated_skill_when_the_credentials_cannot_be_read() -> None:
    meta = _google_workspace_metadata()

    with patch("app.database.connection.get_session", side_effect=RuntimeError("db unavailable")):
        await enrich_skill_metadata_integration_oauth([meta])

    assert (meta.available, meta.unavailable_reason) == (False, GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE)


@pytest.mark.asyncio
async def test_enriching_keeps_a_skill_that_merely_declares_an_issuer_when_the_credentials_cannot_be_read() -> None:
    meta = SkillMetadata(
        name="notes-sync",
        description="Sync notes",
        storage_skill_id="notes-sync",
        storage_path="skills/prebuilt/notes-sync",
        trust=SkillTrust.TRUSTED,
        required_oauth_issuers=["notion"],
    )

    with patch("app.database.connection.get_session", side_effect=RuntimeError("db unavailable")):
        await enrich_skill_metadata_integration_oauth([meta])

    assert (meta.available, meta.unavailable_reason) == (True, None)


@pytest.mark.asyncio
async def test_enriching_a_skill_that_needs_no_credential_opens_no_session() -> None:
    meta = SkillMetadata(
        name="daily-briefing",
        description="Briefing",
        storage_skill_id="daily-briefing",
        storage_path="skills/prebuilt/daily-briefing",
        trust=SkillTrust.TRUSTED,
    )

    with patch("app.database.connection.get_session") as get_session_mock:
        await enrich_skill_metadata_integration_oauth([meta])

    get_session_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("track", _TRACKS, ids=lambda track: track.value)
@pytest.mark.parametrize("operation", ["load_skills", "list_skills"])
async def test_the_backend_enriches_what_it_serves_for_its_track(operation: str, track: CredentialTrack) -> None:
    meta = _google_workspace_metadata()
    base = MagicMock()
    setattr(base, operation, AsyncMock(return_value=[meta]))
    backend = IntegrationOAuthSkillBackend(base, credential_track=track)
    arguments = (["google-workspace"],) if operation == "load_skills" else ()

    with patch(
        "app.core.skills.gates.oauth_availability.enrich_skill_metadata_integration_oauth",
        AsyncMock(),
    ) as enrich_mock:
        result = await getattr(backend, operation)(*arguments)

    assert result == [meta]
    enrich_mock.assert_awaited_once_with([meta], credential_track=track)


@pytest.mark.asyncio
async def test_the_backend_delegates_resource_methods() -> None:
    base = MagicMock()
    base.get_skill_resources = AsyncMock(return_value=b"data")
    base.list_skill_resources = AsyncMock(return_value=["scripts/a.py"])
    backend = IntegrationOAuthSkillBackend(base)

    data = await backend.get_skill_resources("google-workspace", "scripts/a.py")
    files = await backend.list_skill_resources("google-workspace")

    assert data == b"data"
    assert files == ["scripts/a.py"]


@pytest.mark.asyncio
async def test_the_backend_delegates_get_skill_content() -> None:
    base = MagicMock()
    base.get_skill_content = AsyncMock(return_value="# Skill")
    backend = IntegrationOAuthSkillBackend(base)

    content = await backend.get_skill_content("google-workspace")

    assert content == "# Skill"
    base.get_skill_content.assert_awaited_once_with("google-workspace")


@pytest.mark.parametrize("track", _TRACKS, ids=lambda track: track.value)
def test_wrapping_a_backend_returns_the_gate(track: CredentialTrack) -> None:
    wrapped = wrap_integration_oauth_backend(MagicMock(), credential_track=track)

    assert isinstance(wrapped, IntegrationOAuthSkillBackend)
