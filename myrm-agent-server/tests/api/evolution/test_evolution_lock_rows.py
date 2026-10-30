"""
[INPUT]
- app.api.skills.evolution.derive / fix (POS: user-driven evolution triggers)
- app.api.skills.config::toggle_evolution_lock (POS: Skills page lock toggle)
- app.core.skills.store.evolution_store::find_evolution_records (POS: evolution rows of one skill)
[OUTPUT]
- Tests that a page skill id reaches the evolution row keyed by the skill name, and that a locked skill is refused.
[POS]
A skill's evolution rows are not keyed alike (draft approval and auto extraction key by the skill name, batch
import by a generated id). The lock toggle, /derive and /fix take the page id or a row reference, so each must find
the row of any key, and refuse a locked skill up front instead of accepting a request the engine drops.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.skills.evolution import EvolutionType, SkillLineage, SkillRecord, SkillStore

from app.core.skills.models import Skill
from app.core.storage.types import SkillType
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("evolution", "skills")

_PAGE_ID = "local::0123abcd"
_UNLOCKED = "---\nname: demo\ndescription: Demo skill.\n---\n"
_FILE_LOCKED = "---\nname: demo\ndescription: Demo skill.\nevolution-locked: true\n---\n"
_DERIVE = {"instruction": "Cover the empty input case."}


def _row(skill_id: str, skill_md: Path, *, locked: bool = False) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        name="demo",
        description="Demo skill.",
        content=_UNLOCKED,
        path=str(skill_md),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
        evolution_locked=locked,
    )


async def _until(condition: Callable[[], object]) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("background evolution task did not run")


@pytest.fixture
def skill_md(tmp_path: Path) -> Path:
    path = tmp_path / "demo" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(_UNLOCKED, encoding="utf-8")
    return path


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SkillStore]:
    skill_store = SkillStore(db_path=tmp_path / "skills.db")
    yield skill_store
    skill_store.close()


@pytest.fixture
def evolution(store: SkillStore, skill_md: Path) -> Iterator[SimpleNamespace]:
    page_skill = Skill(
        id=_PAGE_ID,
        type=SkillType.LOCAL,
        name="demo",
        description="Demo skill.",
        storage_path=str(skill_md.parent),
    )
    integration = SimpleNamespace(
        store=store,
        engine=MagicMock(derive_skill_simple=AsyncMock(return_value=None)),
        queue=MagicMock(enqueue=AsyncMock()),
    )
    with (
        patch("app.core.skills.store.evolution_store.get_evolution_skill_store", return_value=store),
        patch(
            "myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration",
            return_value=integration,
        ),
        patch(
            "app.core.skills.store.service.skills_service.get_skill",
            new=AsyncMock(side_effect=lambda ref: page_skill if ref == _PAGE_ID else None),
        ),
    ):
        yield integration


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def test_derive_finds_the_row_keyed_by_name_from_the_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("demo", skill_md))

    response = await client.post(f"/api/v1/evolution/derive/{_PAGE_ID}", json=_DERIVE)

    assert response.status_code == 200
    await _until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == "demo"


async def test_derive_finds_a_row_by_the_skill_name_when_the_ref_is_not_a_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("row-1", skill_md))

    response = await client.post("/api/v1/evolution/derive/demo", json=_DERIVE)

    assert response.status_code == 200
    await _until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == "row-1"


async def test_derive_prefers_the_row_keyed_by_the_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("demo", skill_md))
    await store.save_skill(_row(_PAGE_ID, skill_md))

    response = await client.post(f"/api/v1/evolution/derive/{_PAGE_ID}", json=_DERIVE)

    assert response.status_code == 200
    await _until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == _PAGE_ID


async def test_a_row_of_another_skill_with_the_same_name_is_not_adopted(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    other = tmp_path / "elsewhere" / "demo" / "SKILL.md"
    other.parent.mkdir(parents=True)
    other.write_text(_UNLOCKED, encoding="utf-8")
    await store.save_skill(_row("demo", other))

    response = await client.post(f"/api/v1/evolution/derive/{_PAGE_ID}", json=_DERIVE)

    assert response.status_code == 404


async def test_derive_without_any_row_is_not_found(client: AsyncClient, evolution: SimpleNamespace) -> None:
    response = await client.post(f"/api/v1/evolution/derive/{_PAGE_ID}", json=_DERIVE)

    assert response.status_code == 404


async def test_derive_refuses_a_skill_locked_in_the_store(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("demo", skill_md, locked=True))

    response = await client.post(f"/api/v1/evolution/derive/{_PAGE_ID}", json=_DERIVE)

    assert response.status_code == 409
    evolution.engine.derive_skill_simple.assert_not_awaited()


async def test_derive_refuses_a_skill_locked_in_its_file(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("demo", skill_md))
    skill_md.write_text(_FILE_LOCKED, encoding="utf-8")

    response = await client.post(f"/api/v1/evolution/derive/{_PAGE_ID}", json=_DERIVE)

    assert response.status_code == 409
    evolution.engine.derive_skill_simple.assert_not_awaited()


async def test_fix_finds_the_row_keyed_by_name_from_the_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("demo", skill_md))

    response = await client.post(f"/api/v1/evolution/fix/{_PAGE_ID}", json={"reason": "broken"})

    assert response.status_code == 200
    await _until(lambda: evolution.queue.enqueue.await_count)
    assert evolution.queue.enqueue.await_args.args[0].skill_id == "demo"


@pytest.mark.parametrize("file_locked", [False, True], ids=["store-lock", "file-lock"])
async def test_fix_refuses_a_locked_skill_even_when_the_retry_is_forced(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace, file_locked: bool
) -> None:
    await store.save_skill(_row("demo", skill_md, locked=not file_locked))
    if file_locked:
        skill_md.write_text(_FILE_LOCKED, encoding="utf-8")

    response = await client.post("/api/v1/evolution/fix/demo", json={"reason": "broken", "force_retry": True})

    assert response.status_code == 409
    evolution.queue.enqueue.assert_not_awaited()


async def test_unlock_clears_the_row_keyed_by_name_and_the_file(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("demo", skill_md, locked=True))
    skill_md.write_text(_FILE_LOCKED, encoding="utf-8")

    response = await client.post(f"/api/v1/skills/{_PAGE_ID}/evolution-lock", params={"locked": "false"})

    assert response.status_code == 200
    assert store.is_evolution_locked("demo") is False
    assert "evolution-locked: false" in skill_md.read_text(encoding="utf-8")


async def test_lock_marks_every_row_of_the_skill(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(_row("demo", skill_md))
    await store.save_skill(_row(_PAGE_ID, skill_md))

    response = await client.post(f"/api/v1/skills/{_PAGE_ID}/evolution-lock", params={"locked": "true"})

    assert response.status_code == 200
    assert store.is_evolution_locked("demo") is True
    assert store.is_evolution_locked(_PAGE_ID) is True
