"""Integration tests: Google Workspace OAuth ↔ Skills Catalog ↔ Agent runtime.

No mocks on oauth_store, prebuilt sync, or IntegrationOAuthSkillBackend enrichment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.skills import prebuilt_sync
from app.core.skills.loader import create_skill_backend
from app.core.skills.oauth_availability import GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE, GOOGLE_WORKSPACE_SKILL_ID
from app.core.skills.store.service import SkillsService
from app.database.models import Base
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import upsert_oauth_credential
from tests.support.minimal_app import API_PREFIX, build_minimal_app


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
) -> SkillsService:
    service = SkillsService(storage=skills_storage)
    monkeypatch.setattr("app.core.skills.store.service.skills_service", service)
    monkeypatch.setattr("app.platform_utils.get_storage_provider", lambda: skills_storage)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: integration_db)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: integration_db)
    return service


@pytest.fixture
async def skills_client(
    integration_db: async_sessionmaker[AsyncSession],
    skills_storage: LocalStorageBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[TestClient]:
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(skills_storage)

    _patch_integration_db(monkeypatch, integration_db, skills_storage)
    monkeypatch.setattr(
        "app.core.skills.oauth_availability._is_xai_provider_configured",
        lambda: _always_false(),
    )
    app = build_minimal_app(preset="skills_api")
    yield TestClient(app)


async def _always_false() -> bool:
    return False


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

    async with integration_db() as db:
        await upsert_oauth_credential(
            db,
            GOOGLE_WORKSPACE_ISSUER,
            {"token": "integration-access-token", "refresh_token": "rt", "token_url": "https://oauth2.googleapis.com/token"},
        )

    _patch_integration_db(monkeypatch, integration_db, skills_storage)

    backend = await create_skill_backend(
        storage=skills_storage,
        allowed_prebuilt_ids=frozenset({GOOGLE_WORKSPACE_SKILL_ID}),
    )
    skills = await backend.list_skills()
    gw = next(s for s in skills if s.name == GOOGLE_WORKSPACE_SKILL_ID)

    assert gw.available is True
