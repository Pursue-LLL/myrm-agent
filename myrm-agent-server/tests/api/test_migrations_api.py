from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import Base, PendingMigration
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="migrations_api")
from app.platform_utils import get_database_engine


@pytest.fixture
async def async_client():
    pass
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def ensure_pending_migration_table() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
async def cleanup_pending_migrations():
    yield
    async with get_session() as db:
        await db.execute(delete(PendingMigration))
        await db.commit()


@pytest.mark.asyncio
async def test_submit_memory_migration_stages_review_record(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/migrations/memory/submit",
        json={
            "source": "openclaw",
            "version": 1,
            "skip_duplicates": True,
            "description": "导入外部历史记忆",
            "data": {
                "semantic": [{"content": "The user values deterministic migrations."}],
                "episodic": [{"content": "Migrated from OpenClaw on 2026-04-17."}],
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["total_items"] == 2

    async with get_session() as db:
        record = await db.get(PendingMigration, body["migration_id"])
        assert record is not None
        assert record.source == "openclaw"
        assert record.status == "pending"
        assert record.item_counts == {"semantic": 1, "episodic": 1}


@pytest.mark.asyncio
async def test_list_pending_migrations_includes_target_agent_fields(async_client: AsyncClient) -> None:
    agent_id = "agent-list-bind-test"
    submit = await async_client.post(
        "/api/v1/migrations/skills/submit",
        json={
            "source": "hermes",
            "target_agent_id": agent_id,
            "skills": [{"name": "lint", "content": "---\nname: lint\n---\nLint", "source": "hermes"}],
        },
    )
    assert submit.status_code == 200

    response = await async_client.get("/api/v1/migrations/pending")
    assert response.status_code == 200
    body = response.json()
    matched = next(
        (item for item in body["items"] if item["id"] == submit.json()["migration_id"]),
        None,
    )
    assert matched is not None
    assert matched["target_agent_id"] == agent_id


@pytest.mark.asyncio
async def test_list_pending_migrations_returns_staged_records(async_client: AsyncClient) -> None:
    pending_id = uuid.uuid4().hex
    async with get_session() as db:
        db.add(
            PendingMigration(
                id=pending_id,
                source="hermes",
                migration_type="memory_import",
                summary="Pending migration from hermes (1 items; semantic:1)",
                total_items=1,
                item_counts={"semantic": 1},
                payload={"version": 1, "skip_duplicates": True, "data": {"semantic": [{"content": "x"}]}},
                status="pending",
            )
        )
        await db.commit()

    response = await async_client.get("/api/v1/migrations/pending")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(item["id"] == pending_id for item in body["items"])


@pytest.mark.asyncio
async def test_approve_skill_migration_writes_local_skill(
    async_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir = tmp_path / "skills"
    monkeypatch.setattr(
        "app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS",
        [str(skills_dir)],
    )

    submit = await async_client.post(
        "/api/v1/migrations/skills/submit",
        json={
            "source": "hermes",
            "skills": [{"name": "deploy", "content": "---\nname: deploy\n---\nDeploy", "source": "hermes"}],
        },
    )
    assert submit.status_code == 200
    migration_id = submit.json()["migration_id"]

    approve = await async_client.post(f"/api/v1/migrations/pending/{migration_id}/approve")
    assert approve.status_code == 200
    assert (skills_dir / "deploy" / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_submit_skill_migration_persists_target_agent_id(async_client: AsyncClient) -> None:
    agent_id = "agent-migration-bind-test"
    response = await async_client.post(
        "/api/v1/migrations/skills/submit",
        json={
            "source": "hermes",
            "target_agent_id": agent_id,
            "skills": [{"name": "lint", "content": "---\nname: lint\n---\nLint", "source": "hermes"}],
        },
    )
    assert response.status_code == 200
    migration_id = response.json()["migration_id"]

    async with get_session() as db:
        record = await db.get(PendingMigration, migration_id)
        assert record is not None
        assert record.payload.get("target_agent_id") == agent_id


@pytest.mark.asyncio
async def test_approve_skill_migration_binds_target_agent(
    async_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir = tmp_path / "skills"
    agent_id = "agent-bind-on-approve"
    monkeypatch.setattr(
        "app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS",
        [str(skills_dir)],
    )

    submit = await async_client.post(
        "/api/v1/migrations/skills/submit",
        json={
            "source": "hermes",
            "target_agent_id": agent_id,
            "skills": [{"name": "deploy", "content": "---\nname: deploy\n---\nDeploy", "source": "hermes"}],
        },
    )
    migration_id = submit.json()["migration_id"]

    profile = MagicMock()
    profile.skills = []
    update_mock = AsyncMock(return_value=object())
    with (
        patch(
            "app.services.migration.skill_binding.AgentService.get_agent_by_id",
            new=AsyncMock(return_value=profile),
        ),
        patch(
            "app.services.migration.skill_binding.AgentService.update_agent",
            new=update_mock,
        ),
    ):
        approve = await async_client.post(f"/api/v1/migrations/pending/{migration_id}/approve")

    assert approve.status_code == 200
    update_mock.assert_awaited_once()
