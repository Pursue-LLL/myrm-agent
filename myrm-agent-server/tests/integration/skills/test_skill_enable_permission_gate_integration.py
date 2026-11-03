"""Integration: enabling a skill that declares permissions asks for them first.

A preset skill and a skill folder the user keeps declare ``required_permissions`` in their own SKILL.md. The catalog, the
preset sync, the local scan, the enable gate, the grant endpoint and the user config run without mocks; only the
database, the storage and the folders the preset sync and the local scan read are the test's own, so the cases do not
depend on which preset skills the product ships.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.skills import models as skill_models
from app.core.skills import prebuilt_sync
from app.core.skills.store.service import skills_service
from app.database.models import Base
from tests.support.minimal_app import API_PREFIX, build_minimal_app

SKILL_ID = "reads-the-workspace"
SKILL_API = f"{API_PREFIX}/skills/{SKILL_ID}"
SEED_SKILL_MD = f"""---
name: {SKILL_ID}
description: Reads the files the user names.
required_permissions:
  - file_read
---
# {SKILL_ID}

Read the files the user names.
"""
LOCAL_SKILL_NAME = "reads-then-writes"
# Declared out of order: the permissions the response names come back sorted.
LOCAL_SKILL_MD = f"""---
name: {LOCAL_SKILL_NAME}
description: Copies a file after reading it.
required_permissions:
  - file_write
  - file_read
---
# {LOCAL_SKILL_NAME}

Read the file, then write the copy.
"""


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
    seeds_dir = tmp_path / "seeds"
    (seeds_dir / SKILL_ID).mkdir(parents=True)
    (seeds_dir / SKILL_ID / "SKILL.md").write_text(SEED_SKILL_MD, encoding="utf-8")
    monkeypatch.setattr(prebuilt_sync, "SEEDS_DIR", seeds_dir)
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


@pytest.fixture
def local_skill_api(skills_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """The API path of a skill folder the user keeps, found by the real local scan of a folder of the test's own."""
    skills_root = tmp_path / "local-skills"
    (skills_root / LOCAL_SKILL_NAME).mkdir(parents=True)
    (skills_root / LOCAL_SKILL_NAME / "SKILL.md").write_text(LOCAL_SKILL_MD, encoding="utf-8")
    # The scan reads these roots; the user's own skill folders stay out of the test.
    monkeypatch.setattr(skill_models, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_root)])
    monkeypatch.setattr("app.core.skills.providers.local.DEFAULT_LOCAL_SKILL_PATHS", [str(skills_root)])

    scanned = skills_client.post(f"{API_PREFIX}/skills/local/scan")
    assert scanned.status_code == 200, scanned.text
    skill_ids = [skill["id"] for skill in scanned.json()["skills"] if skill["name"] == LOCAL_SKILL_NAME]
    assert len(skill_ids) == 1, scanned.text
    return f"{API_PREFIX}/skills/{skill_ids[0]}"


def _enabled_local_skill_ids(client: TestClient) -> list[str]:
    response = client.get(f"{API_PREFIX}/skills/config")
    assert response.status_code == 200, response.text
    enabled_ids: list[str] = response.json()["enabled_local_skill_ids"]
    return enabled_ids


def test_a_local_skill_asks_for_every_permission_its_skill_file_declares(skills_client: TestClient, local_skill_api: str) -> None:
    response = skills_client.post(f"{local_skill_api}/enable")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pending_approval"] is True
    assert body["enabled"] is False
    assert body["required_permissions"] == ["file_read", "file_write"]
    assert _enabled_local_skill_ids(skills_client) == []


def test_only_the_permissions_that_are_still_missing_are_asked_for(skills_client: TestClient, local_skill_api: str) -> None:
    skills_client.post(f"{local_skill_api}/permissions/grant", json={"permissions": ["file_read"]})

    half_granted = skills_client.post(f"{local_skill_api}/enable")

    assert half_granted.json()["pending_approval"] is True
    assert half_granted.json()["required_permissions"] == ["file_write"]
    assert _enabled_local_skill_ids(skills_client) == []

    skills_client.post(f"{local_skill_api}/permissions/grant", json={"permissions": ["file_write"]})
    fully_granted = skills_client.post(f"{local_skill_api}/enable")

    assert fully_granted.json()["enabled"] is True
    assert len(_enabled_local_skill_ids(skills_client)) == 1
