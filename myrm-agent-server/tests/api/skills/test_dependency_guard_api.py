"""API tests for skill dependency impact surfacing and management guards.

Covers the three server-side dependency integrations of the roadmap item:
- growth/pending review payloads expose ``impacted_dependents``
- disable is blocked with DEPENDENTS_EXIST unless ``force`` is set
- force bypass proceeds with the underlying disable flow
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord
from sqlalchemy import delete

from app.api.skills.config import router as config_router
from app.api.skills.evolution import router as evolution_router
from app.api.skills.growth import router as growth_router
from app.core.skills.store.evolution_store import get_evolution_skill_store
from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine, reset_database_engine
from app.services.skills.evolution_reviews import create_evolution_review_record


def _skill_record(skill_id: str, name: str, content: str) -> SkillRecord:
    """Build a minimal SkillRecord for seeding the evolution store."""
    return SkillRecord(
        skill_id=skill_id,
        name=name,
        description=f"desc {name}",
        content=content,
        path=f"skills/{name}.md",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
    )


async def _seed_dependency_graph() -> None:
    """Persist base-skill plus a dependent that declares it in dependencies."""
    store = get_evolution_skill_store()
    await store.save_skill(_skill_record("base-skill", "base-skill", "---\nname: base-skill\n---\nplain"))
    await store.save_skill(
        _skill_record(
            "dep-skill",
            "dep-skill",
            "---\nname: dep-skill\ndependencies:\n  - base-skill\n---\nplain",
        )
    )


@pytest.fixture
def patch_evolution_store(tmp_path: Path) -> Path:
    """Point the shared evolution store at an isolated temp database."""
    from app.core.skills.store.evolution_store import reset_evolution_skill_store

    reset_evolution_skill_store()
    db_path = tmp_path / "skills.db"
    with patch(
        "app.core.skills.store.evolution_store.get_evolution_skill_store_db_path",
        return_value=db_path,
    ):
        yield db_path
    reset_evolution_skill_store()


@pytest.fixture(scope="function")
def app() -> FastAPI:
    test_app = FastAPI(title="Skill Dependency Guard Test App")
    test_app.include_router(growth_router, prefix="/api/v1", tags=["skill-growth"])
    test_app.include_router(evolution_router, prefix="/api/v1", tags=["evolution"])
    test_app.include_router(config_router, prefix="/api/v1/skills", tags=["skills-config"])
    return test_app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
async def setup_database() -> None:
    await reset_database_engine()
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()
    await reset_database_engine()


async def _seed_pending_evolution_for_base_skill() -> str:
    """Create a pending evolution review targeting base-skill and return its id."""
    record = await create_evolution_review_record(
        agent_id="dep-guard-test",
        chat_id=None,
        proposal_skill_id="base-skill",
        skill_name="base-skill",
        skill_path="/tmp/base-skill.md",
        evolution_type="fix",
        reason="impacted dependents regression",
        original_content="old",
        evolved_content="new",
        confidence=0.8,
        test_passed=True,
        task_context="dependency guard api",
    )
    return record.id


@pytest.mark.asyncio
async def test_growth_cases_surface_impacted_dependents(
    client: TestClient,
    setup_database: None,
    patch_evolution_store: Path,
) -> None:
    await _seed_dependency_graph()
    evolution_id = await _seed_pending_evolution_for_base_skill()

    response = client.get("/api/v1/skill-growth/cases?limit=10")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    item = next(i for i in items if i["id"] == f"evolution:{evolution_id}")
    assert item["impacted_dependents"] == ["dep-skill"]

    detail = client.get(f"/api/v1/skill-growth/cases/evolution:{evolution_id}").json()["data"]
    assert detail["impacted_dependents"] == ["dep-skill"]


@pytest.mark.asyncio
async def test_pending_reviews_surface_impacted_dependents(
    client: TestClient,
    setup_database: None,
    patch_evolution_store: Path,
) -> None:
    await _seed_dependency_graph()
    await _seed_pending_evolution_for_base_skill()

    response = client.get("/api/v1/evolution/pending")
    assert response.status_code == 200
    item = next(i for i in response.json()["items"] if i["skill_id"] == "base-skill")
    assert item["impacted_dependents"] == ["dep-skill"]

    list_body = client.get("/api/v1/evolution/pending").json()
    detail_id = next(i["id"] for i in list_body["items"] if i["skill_id"] == "base-skill")
    detail = client.get(f"/api/v1/evolution/pending/{detail_id}").json()
    assert detail["impacted_dependents"] == ["dep-skill"]


@pytest.mark.asyncio
async def test_disable_blocks_when_dependents_exist(
    client: TestClient,
    patch_evolution_store: Path,
) -> None:
    await _seed_dependency_graph()

    response = client.post("/api/v1/skills/base-skill/disable")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "DEPENDENTS_EXIST"
    assert detail["impacted_dependents"] == ["dep-skill"]


@pytest.mark.asyncio
async def test_disable_force_bypasses_dependency_guard(
    client: TestClient,
    patch_evolution_store: Path,
) -> None:
    await _seed_dependency_graph()

    from app.core.skills.models import UserSkillConfig
    from app.core.skills.store.service import skills_service

    config = UserSkillConfig(user_id="dep-guard-test")
    with (
        patch.object(skills_service.user_config, "get_config", new=AsyncMock(return_value=config)),
        patch.object(skills_service.user_config, "disable_prebuilt_skill", new=AsyncMock()),
        patch("app.api.skills.config.bump_skill_config_version", new=MagicMock()),
        patch("app.api.skills.config._audit_skill_action", new=MagicMock()),
    ):
        response = client.post("/api/v1/skills/base-skill/disable?force=true")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
