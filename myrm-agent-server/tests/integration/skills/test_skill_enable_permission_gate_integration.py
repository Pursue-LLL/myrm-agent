"""Integration: enabling a prebuilt skill that declares permissions asks for them first.

``repo-call-graph`` is the one preset skill that declares ``required_permissions`` (``file_read``). The catalog,
the enable gate, the grant endpoint and the user config run without mocks; only the database and the storage are
the test's own.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.skills import prebuilt_sync
from app.core.skills.store.service import skills_service
from app.database.models import Base
from tests.support.minimal_app import API_PREFIX, build_minimal_app

SKILL_ID = "repo-call-graph"
SKILL_API = f"{API_PREFIX}/skills/{SKILL_ID}"


@pytest.fixture
async def skills_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[TestClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    storage = LocalStorageBackend(str(tmp_path / "storage"))

    # API modules bind ``skills_service`` at import time, so the shared instance is pointed at the test storage and
    # database instead of being swapped.
    monkeypatch.setattr(skills_service, "_storage", storage)  # noqa: SLF001
    monkeypatch.setattr(skills_service, "_user_config", None)  # noqa: SLF001
    monkeypatch.setattr(skills_service, "_local_skills", None)  # noqa: SLF001
    monkeypatch.setattr("app.platform_utils.get_storage_provider", lambda: storage)
    monkeypatch.setattr("app.platform_utils.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.database.connection.get_session_factory", lambda: factory)
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    yield TestClient(build_minimal_app(preset="skills_api"))
    await engine.dispose()


def _enabled_prebuilt_ids(client: TestClient) -> list[str]:
    response = client.get(f"{API_PREFIX}/skills/config")
    assert response.status_code == 200, response.text
    enabled_ids: list[str] = response.json()["enabled_prebuilt_ids"]
    return enabled_ids


def test_the_catalog_lists_the_permission_the_skill_declares(skills_client: TestClient) -> None:
    response = skills_client.get(f"{SKILL_API}/permissions/required")
    assert response.status_code == 200, response.text
    assert response.json()["required_permissions"] == ["file_read"]


def test_enabling_asks_for_the_declared_permission_before_the_skill_is_switched_on(skills_client: TestClient) -> None:
    response = skills_client.post(f"{SKILL_API}/enable")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pending_approval"] is True
    assert body["enabled"] is False
    assert body["required_permissions"] == ["file_read"]
    assert SKILL_ID not in _enabled_prebuilt_ids(skills_client)


def test_the_skill_is_switched_on_once_the_permission_is_granted(skills_client: TestClient) -> None:
    granted = skills_client.post(f"{SKILL_API}/permissions/grant", json={"permissions": ["file_read"]})
    assert granted.status_code == 200, granted.text
    assert granted.json()["granted_permissions"] == ["file_read"]

    response = skills_client.post(f"{SKILL_API}/enable")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert not body["pending_approval"]
    assert SKILL_ID in _enabled_prebuilt_ids(skills_client)


def test_revoking_the_permission_makes_the_next_enable_ask_again(skills_client: TestClient) -> None:
    skills_client.post(f"{SKILL_API}/permissions/grant", json={"permissions": ["file_read"]})
    skills_client.post(f"{SKILL_API}/disable")
    revoked = skills_client.post(f"{SKILL_API}/permissions/revoke", json={"permissions": ["file_read"]})
    assert revoked.status_code == 200, revoked.text

    response = skills_client.post(f"{SKILL_API}/enable")

    assert response.json()["pending_approval"] is True
    assert SKILL_ID not in _enabled_prebuilt_ids(skills_client)
