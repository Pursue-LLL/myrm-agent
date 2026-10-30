"""Evolution API tests — bypass auth for TestClient (non-loopback client).

Also the shared wiring of the skill-row tests: a real ``SkillStore`` on a temp file, the evolution integration with a
mocked engine and queue, and an HTTP client on the evolution and skills routers.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.skills.evolution import EvolutionType, SkillLineage, SkillRecord, SkillStore
from sqlalchemy import delete

from app.core.security.auth.identity import LOCAL_USER_ID
from app.core.skills.models import Skill
from app.core.storage.types import SkillType
from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine
from tests.support.minimal_app import build_minimal_app

PAGE_ID = "local::0123abcd"
PREBUILT_ID = "prebuilt-demo"
UNLOCKED = "---\nname: demo\ndescription: Demo skill.\n---\n"
FILE_LOCKED = "---\nname: demo\ndescription: Demo skill.\nevolution-locked: true\n---\n"
DERIVE = {"instruction": "Cover the empty input case."}


def evolution_row(skill_id: str, skill_md: Path, *, name: str = "demo", locked: bool = False) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        name=name,
        description="Demo skill.",
        content=UNLOCKED,
        path=str(skill_md),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
        evolution_locked=locked,
    )


async def until(condition: Callable[[], object]) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("background evolution task did not run")


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture(autouse=True)
async def ensure_tables() -> AsyncIterator[None]:
    """Ensure DB tables exist for all evolution tests."""
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.fixture
def skill_md(tmp_path: Path) -> Path:
    path = tmp_path / "demo" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(UNLOCKED, encoding="utf-8")
    return path


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SkillStore]:
    skill_store = SkillStore(db_path=tmp_path / "skills.db")
    yield skill_store
    skill_store.close()


@pytest.fixture
def evolution(store: SkillStore, skill_md: Path) -> Iterator[SimpleNamespace]:
    """The evolution integration; ``pages`` is what the Skills page service knows, by skill id."""
    pages = {
        PAGE_ID: Skill(
            id=PAGE_ID,
            type=SkillType.LOCAL,
            name="demo",
            description="Demo skill.",
            storage_path=str(skill_md.parent),
        ),
        PREBUILT_ID: Skill(
            id=PREBUILT_ID,
            type=SkillType.PREBUILT,
            name="demo",
            description="Demo skill.",
            storage_path=str(skill_md.parent),
        ),
    }
    integration = SimpleNamespace(
        store=store,
        engine=MagicMock(derive_skill_simple=AsyncMock(return_value=None)),
        queue=MagicMock(enqueue=AsyncMock()),
        pages=pages,
    )
    with (
        patch("app.core.skills.store.evolution_store.get_evolution_skill_store", return_value=store),
        patch(
            "myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration",
            return_value=integration,
        ),
        patch(
            "app.core.skills.store.service.skills_service.get_skill",
            new=AsyncMock(side_effect=pages.get),
        ),
    ):
        yield integration


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = build_minimal_app("evolution", "skills")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
