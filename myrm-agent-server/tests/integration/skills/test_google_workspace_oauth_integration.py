"""Integration tests: stored credentials ↔ Skills Catalog ↔ Agent runtime (Google Workspace OAuth, xAI provider key).

No mocks on oauth_store, the config readers, prebuilt sync, or IntegrationOAuthSkillBackend enrichment: the credentials
are rows of the scratch database, read back by the production gate.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.security import CredentialTrack
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai_agents.custom_agent_factory import CustomAgentFactory
from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog
from app.core.skills import prebuilt_sync
from app.core.skills.gates.oauth_availability import (
    GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    GOOGLE_WORKSPACE_SKILL_ID,
    X_LIVE_SEARCH_SKILL_ID,
    X_LIVE_SEARCH_UNAVAILABLE,
)
from app.core.skills.loader import create_skill_backend
from app.core.skills.store.user_config import UserSkillConfigManager
from app.database.models import Base
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import upsert_oauth_credential
from tests.support.minimal_app import API_PREFIX, build_minimal_app
from tests.support.skill_credential_store import CredentialState, CredentialStore, bind_credential_readers


@pytest.fixture
async def integration_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def skills_storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path / "storage"))


def _patch_integration_db(
    monkeypatch: pytest.MonkeyPatch,
    integration_db: async_sessionmaker[AsyncSession],
    skills_storage: LocalStorageBackend,
) -> CredentialStore:
    """Route the skills service and every credential reader to the scratch storage and database.

    Credentials are stored through the returned store, after this call: the rows are encrypted with the key it binds.
    """
    from app.core.skills.store.service import skills_service

    # API modules bind `skills_service` at import time; rebinding the shared
    # instance's storage (not swapping the instance) keeps every already-imported
    # module pointing at the same service while routing it to the test storage/DB.
    # setattr(instance, ...) registers automatic teardown restore.
    monkeypatch.setattr(skills_service, "_storage", skills_storage)  # noqa: SLF001
    monkeypatch.setattr(skills_service, "_user_config", None)  # noqa: SLF001
    monkeypatch.setattr(skills_service, "_local_skills", None)  # noqa: SLF001
    monkeypatch.setattr("app.core.skills.store.service.skills_service", skills_service)
    monkeypatch.setattr("app.platform_utils.get_storage_provider", lambda: skills_storage)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: integration_db)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: integration_db)
    return bind_credential_readers(monkeypatch, integration_db)


@pytest.fixture
async def skills_client(
    integration_db: async_sessionmaker[AsyncSession],
    skills_storage: LocalStorageBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[TestClient]:
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(skills_storage)

    _patch_integration_db(monkeypatch, integration_db, skills_storage)
    app = build_minimal_app(preset="skills_api")
    yield TestClient(app)


def test_catalog_lists_google_workspace_unavailable_without_oauth(
    skills_client: TestClient,
) -> None:
    response = skills_client.get(f"{API_PREFIX}/skills/?type=prebuilt")
    assert response.status_code == 200, response.text

    skill = next(s for s in response.json()["skills"] if s["id"] == GOOGLE_WORKSPACE_SKILL_ID)
    assert skill["available"] is False
    assert skill["unavailable_reason"] == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


def test_get_skill_detail_unavailable_without_oauth(skills_client: TestClient) -> None:
    response = skills_client.get(f"{API_PREFIX}/skills/{GOOGLE_WORKSPACE_SKILL_ID}")
    assert response.status_code == 200, response.text

    skill = response.json()
    assert skill["id"] == GOOGLE_WORKSPACE_SKILL_ID
    assert skill["available"] is False
    assert skill["unavailable_reason"] == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


def test_get_available_skills_marks_google_workspace_unavailable_without_oauth(
    skills_client: TestClient,
) -> None:
    enable_resp = skills_client.post(f"{API_PREFIX}/skills/{GOOGLE_WORKSPACE_SKILL_ID}/enable")
    assert enable_resp.status_code == 200, enable_resp.text

    response = skills_client.get(f"{API_PREFIX}/skills/available")
    assert response.status_code == 200, response.text

    skill = next(s for s in response.json()["skills"] if s["id"] == GOOGLE_WORKSPACE_SKILL_ID)
    assert skill["available"] is False
    assert skill["unavailable_reason"] == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_catalog_lists_google_workspace_available_when_oauth_connected(
    skills_client: TestClient,
    integration_db: async_sessionmaker[AsyncSession],
) -> None:
    async with integration_db() as db:
        await upsert_oauth_credential(
            db,
            GOOGLE_WORKSPACE_ISSUER,
            {"token": "integration-access-token", "refresh_token": "rt", "token_url": "https://oauth2.googleapis.com/token"},
        )

    response = skills_client.get(f"{API_PREFIX}/skills/?type=prebuilt")
    assert response.status_code == 200, response.text

    skill = next(s for s in response.json()["skills"] if s["id"] == GOOGLE_WORKSPACE_SKILL_ID)
    assert skill["available"] is True
    assert skill["unavailable_reason"] is None


@pytest.mark.asyncio
async def test_loader_runtime_marks_google_workspace_unavailable_without_oauth(
    skills_storage: LocalStorageBackend,
    integration_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(skills_storage)
    _patch_integration_db(monkeypatch, integration_db, skills_storage)

    backend = await create_skill_backend(
        storage=skills_storage,
        allowed_prebuilt_ids=frozenset({GOOGLE_WORKSPACE_SKILL_ID}),
    )
    skills = await backend.list_skills()
    gw = next(s for s in skills if s.name == GOOGLE_WORKSPACE_SKILL_ID)

    assert gw.available is False
    assert gw.unavailable_reason == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_loader_runtime_available_when_oauth_connected(
    skills_storage: LocalStorageBackend,
    integration_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(skills_storage)
    credentials = _patch_integration_db(monkeypatch, integration_db, skills_storage)
    await credentials.store_oauth(
        {
            GOOGLE_WORKSPACE_ISSUER: {
                "token": "integration-access-token",
                "refresh_token": "rt",
                "token_url": "https://oauth2.googleapis.com/token",
            }
        }
    )

    backend = await create_skill_backend(
        storage=skills_storage,
        allowed_prebuilt_ids=frozenset({GOOGLE_WORKSPACE_SKILL_ID}),
    )
    skills = await backend.list_skills()
    gw = next(s for s in skills if s.name == GOOGLE_WORKSPACE_SKILL_ID)

    assert gw.available is True


@pytest.mark.asyncio
async def test_catalog_lists_x_live_search_available_for_an_install_with_only_a_provider_key(
    skills_client: TestClient,
    integration_db: async_sessionmaker[AsyncSession],
) -> None:
    await CredentialStore(integration_db).seed(CredentialState(xai_provider="key"))

    response = skills_client.get(f"{API_PREFIX}/skills/?type=prebuilt")
    assert response.status_code == 200, response.text

    skill = next(s for s in response.json()["skills"] if s["id"] == X_LIVE_SEARCH_SKILL_ID)
    assert skill["available"] is True
    assert skill["unavailable_reason"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("track", "listed"),
    [(CredentialTrack.PERSONAL, True), (CredentialTrack.SHARED, False)],
    ids=lambda value: getattr(value, "value", str(value)),
)
async def test_loader_runtime_lists_x_live_search_for_the_track_it_is_built_for(
    skills_storage: LocalStorageBackend,
    integration_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    track: CredentialTrack,
    listed: bool,
) -> None:
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(skills_storage)
    credentials = _patch_integration_db(monkeypatch, integration_db, skills_storage)
    await credentials.seed(CredentialState(xai_provider="key"))

    backend = await create_skill_backend(
        storage=skills_storage,
        allowed_prebuilt_ids=frozenset({X_LIVE_SEARCH_SKILL_ID}),
        credential_track=track,
    )
    skill = next(s for s in await backend.list_skills() if s.name == X_LIVE_SEARCH_SKILL_ID)

    assert skill.available is listed
    assert skill.unavailable_reason == (None if listed else X_LIVE_SEARCH_UNAVAILABLE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("track", "listed"),
    [(CredentialTrack.PERSONAL, True), (CredentialTrack.SHARED, False)],
    ids=lambda value: getattr(value, "value", str(value)),
)
async def test_a_delegated_custom_agent_lists_x_live_search_for_the_track_of_the_turn_that_delegates(
    skills_storage: LocalStorageBackend,
    integration_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    track: CredentialTrack,
    listed: bool,
) -> None:
    """The sub-agent runs inside the delegating turn, so it sees the turn's credentials and no others."""
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(skills_storage)
    credentials = _patch_integration_db(monkeypatch, integration_db, skills_storage)
    await credentials.seed(CredentialState(xai_provider="key"))
    await UserSkillConfigManager(skills_storage).enable_prebuilt_skill(X_LIVE_SEARCH_SKILL_ID)

    profile = SimpleNamespace(
        id="researcher",
        display_name="Researcher",
        description="",
        system_prompt="Research.",
        model=None,
        max_iterations=8,
        skills=[X_LIVE_SEARCH_SKILL_ID],
        metadata={},
    )
    monkeypatch.setattr("app.ai_agents.subagent_catalog.get_session_factory", lambda: integration_db)
    monkeypatch.setattr("app.ai_agents.subagent_catalog.AgentService.get_agent_by_id", AsyncMock(return_value=profile))

    config = await DatabaseSubagentCatalog(bound_agent_ids=["researcher"], credential_track=track).resolve("researcher")
    assert config is not None
    factory = config.agent_factory
    assert isinstance(factory, CustomAgentFactory)
    await factory._ensure_initialized()  # noqa: SLF001
    assert factory._cached_skill_backend is not None  # noqa: SLF001

    skill = next(s for s in await factory._cached_skill_backend.list_skills() if s.name == X_LIVE_SEARCH_SKILL_ID)  # noqa: SLF001
    assert skill.available is listed
    assert skill.unavailable_reason == (None if listed else X_LIVE_SEARCH_UNAVAILABLE)
