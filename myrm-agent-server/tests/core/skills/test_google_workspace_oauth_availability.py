"""Tests for integration OAuth availability on prebuilt skills."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillTrust
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.models import Skill
from app.core.skills.oauth_availability import (
    GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    GOOGLE_WORKSPACE_SKILL_ID,
    IntegrationOAuthSkillBackend,
    apply_integration_oauth_availability,
    apply_integration_oauth_to_metadata,
    enrich_skill_metadata_integration_oauth,
    wrap_integration_oauth_backend,
)


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


@pytest.mark.asyncio
async def test_apply_oauth_availability_marks_google_workspace_unavailable() -> None:
    skill = _google_workspace_skill()
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=False),
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is False
    assert skill.unavailable_reason == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_apply_oauth_availability_leaves_connected_skill_available() -> None:
    skill = _google_workspace_skill()
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=True),
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is True
    assert skill.unavailable_reason is None


@pytest.mark.asyncio
async def test_apply_oauth_availability_skips_unrelated_skills() -> None:
    other = Skill(
        id="daily-briefing",
        type=SkillType.PREBUILT,
        name="Daily Briefing",
        description="Morning briefing",
        storage_path="skills/prebuilt/daily-briefing",
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=False),
    ) as connected_mock:
        await apply_integration_oauth_availability([other], db)

    connected_mock.assert_not_awaited()
    assert other.available is True


@pytest.mark.asyncio
async def test_apply_oauth_to_metadata_marks_google_workspace_unavailable() -> None:
    meta = _google_workspace_metadata()
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=False),
    ):
        await apply_integration_oauth_to_metadata([meta], db)

    assert meta.available is False
    assert meta.unavailable_reason == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_apply_oauth_to_metadata_leaves_connected_skill_available() -> None:
    meta = _google_workspace_metadata()
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=True),
    ):
        await apply_integration_oauth_to_metadata([meta], db)

    assert meta.available is True
    assert meta.unavailable_reason is None


@pytest.mark.asyncio
async def test_enrich_skill_metadata_integration_oauth_uses_db_session() -> None:
    meta = _google_workspace_metadata()
    session = AsyncMock()

    class _SessionCtx:
        async def __aenter__(self) -> AsyncMock:
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    with (
        patch("app.database.connection.get_session", return_value=_SessionCtx()),
        patch(
            "app.core.skills.oauth_availability.apply_integration_oauth_to_metadata",
            AsyncMock(),
        ) as apply_mock,
    ):
        await enrich_skill_metadata_integration_oauth([meta])

    apply_mock.assert_awaited_once_with([meta], session)


@pytest.mark.asyncio
async def test_enrich_skill_metadata_integration_oauth_fail_closed_on_db_errors() -> None:
    meta = _google_workspace_metadata()

    with patch(
        "app.database.connection.get_session",
        side_effect=RuntimeError("db unavailable"),
    ):
        await enrich_skill_metadata_integration_oauth([meta])

    assert meta.available is False
    assert meta.unavailable_reason == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_integration_oauth_backend_enriches_load_skills() -> None:
    meta = _google_workspace_metadata()
    base = MagicMock()
    base.load_skills = AsyncMock(return_value=[meta])

    backend = IntegrationOAuthSkillBackend(base)

    with patch(
        "app.core.skills.oauth_availability.enrich_skill_metadata_integration_oauth",
        AsyncMock(),
    ) as enrich_mock:
        result = await backend.load_skills(["google-workspace"])

    assert result == [meta]
    enrich_mock.assert_awaited_once_with([meta])


@pytest.mark.asyncio
async def test_enrich_skill_metadata_skips_unrelated_skills() -> None:
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
async def test_integration_oauth_backend_delegates_resource_methods() -> None:
    base = MagicMock()
    base.get_skill_resources = AsyncMock(return_value=b"data")
    base.list_skill_resources = AsyncMock(return_value=["scripts/a.py"])
    backend = IntegrationOAuthSkillBackend(base)

    data = await backend.get_skill_resources("google-workspace", "scripts/a.py")
    files = await backend.list_skill_resources("google-workspace")

    assert data == b"data"
    assert files == ["scripts/a.py"]


@pytest.mark.asyncio
async def test_integration_oauth_backend_delegates_get_skill_content() -> None:
    base = MagicMock()
    base.get_skill_content = AsyncMock(return_value="# Skill")
    backend = IntegrationOAuthSkillBackend(base)

    content = await backend.get_skill_content("google-workspace")

    assert content == "# Skill"
    base.get_skill_content.assert_awaited_once_with("google-workspace")


def test_wrap_integration_oauth_backend_returns_wrapper() -> None:
    base = MagicMock()
    wrapped = wrap_integration_oauth_backend(base)
    assert isinstance(wrapped, IntegrationOAuthSkillBackend)


@pytest.mark.asyncio
async def test_integration_oauth_backend_enriches_list_skills() -> None:
    meta = _google_workspace_metadata()
    base = MagicMock()
    base.list_skills = AsyncMock(return_value=[meta])

    backend = IntegrationOAuthSkillBackend(base)

    with patch(
        "app.core.skills.oauth_availability.enrich_skill_metadata_integration_oauth",
        AsyncMock(),
    ) as enrich_mock:
        result = await backend.list_skills()

    assert result == [meta]
    enrich_mock.assert_awaited_once_with([meta])
