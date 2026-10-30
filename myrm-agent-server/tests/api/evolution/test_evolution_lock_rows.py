"""
[INPUT]
- app.api.skills.evolution.derive / fix (POS: user-driven evolution triggers)
- app.api.skills.config::toggle_evolution_lock (POS: Skills page lock toggle)
- app.core.skills.store.evolution_store::find_evolution_records, evolution_record_for_page_skill (POS: evolution rows of one skill)
[OUTPUT]
- Tests that a page skill id reaches its evolution row whatever the row is keyed by, that a local skill without a row
  gets one, and that a locked skill is refused.
[POS]
A skill's evolution rows are not keyed alike (draft approval and auto extraction key by the skill name, batch
import by a generated id) and a skill made in chat has none. The lock toggle, /derive and /fix take the page id or a
row reference, so each must find the row of any key, give a local skill without one a row, and refuse a locked skill
up front instead of accepting a request the engine drops.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from myrm_agent_harness.agent.skills.evolution import SkillStore

from tests.api.evolution.conftest import (
    DERIVE,
    FILE_LOCKED,
    PAGE_ID,
    PREBUILT_ID,
    UNLOCKED,
    evolution_row,
    until,
)


async def test_derive_finds_the_row_keyed_by_name_from_the_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("demo", skill_md))

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == "demo"


async def test_derive_finds_a_row_by_the_skill_name_when_the_ref_is_not_a_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("row-1", skill_md))

    response = await client.post("/api/v1/evolution/derive/demo", json=DERIVE)

    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == "row-1"


async def test_derive_prefers_the_row_keyed_by_the_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("demo", skill_md))
    await store.save_skill(evolution_row(PAGE_ID, skill_md))

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == PAGE_ID


async def test_a_row_of_another_skill_with_the_same_name_is_not_adopted(
    client: AsyncClient, store: SkillStore, tmp_path: Path, skill_md: Path, evolution: SimpleNamespace
) -> None:
    other = tmp_path / "elsewhere" / "demo" / "SKILL.md"
    other.parent.mkdir(parents=True)
    other.write_text(UNLOCKED, encoding="utf-8")
    await store.save_skill(evolution_row("demo", other))

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == PAGE_ID
    original, created = store.get_skill("demo"), store.get_skill(PAGE_ID)
    assert original is not None
    assert created is not None
    assert (original.path, created.path) == (str(other), str(skill_md))


async def test_derive_gives_a_local_skill_without_a_row_its_own_row(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert evolution.engine.derive_skill_simple.await_args.kwargs["skill_id"] == PAGE_ID
    created = store.get_skill(PAGE_ID)
    assert created is not None
    assert (created.name, created.path, created.content) == ("demo", str(skill_md), UNLOCKED)
    assert created.evolution_locked is False


async def test_a_repeated_derive_reuses_the_row_it_created(
    client: AsyncClient, store: SkillStore, evolution: SimpleNamespace
) -> None:
    for _ in range(2):
        assert (await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)).status_code == 200

    await until(lambda: evolution.engine.derive_skill_simple.await_count == 2)
    assert [record.skill_id for record in store.get_active_skills()] == [PAGE_ID]


async def test_fix_gives_a_local_skill_without_a_row_its_own_row(
    client: AsyncClient, store: SkillStore, evolution: SimpleNamespace
) -> None:
    response = await client.post(f"/api/v1/evolution/fix/{PAGE_ID}", json={"reason": "broken"})

    assert response.status_code == 200
    await until(lambda: evolution.queue.enqueue.await_count)
    assert evolution.queue.enqueue.await_args.args[0].skill_id == PAGE_ID
    assert store.get_skill(PAGE_ID) is not None


async def test_a_locked_skill_without_a_row_is_refused_and_gets_no_row(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    skill_md.write_text(FILE_LOCKED, encoding="utf-8")

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 409
    assert store.get_skill(PAGE_ID) is None
    evolution.engine.derive_skill_simple.assert_not_awaited()


async def test_a_skill_that_is_not_local_gets_no_row(client: AsyncClient, store: SkillStore, evolution: SimpleNamespace) -> None:
    response = await client.post(f"/api/v1/evolution/derive/{PREBUILT_ID}", json=DERIVE)

    assert response.status_code == 404
    assert store.get_active_skills() == []


async def test_a_local_skill_without_a_skill_md_is_not_found(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    skill_md.unlink()

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 404
    assert store.get_active_skills() == []


async def test_a_skill_md_too_large_to_store_is_rejected_without_a_row(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    skill_md.write_text(UNLOCKED + "x" * (SkillStore.MAX_SKILL_CONTENT_CHARS + 1), encoding="utf-8")

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 422
    assert "too large" in response.json()["detail"]
    assert store.get_active_skills() == []
    evolution.engine.derive_skill_simple.assert_not_awaited()


async def test_an_unknown_skill_is_not_found(client: AsyncClient, evolution: SimpleNamespace) -> None:
    response = await client.post("/api/v1/evolution/derive/local::unknown", json=DERIVE)

    assert response.status_code == 404


async def test_derive_refuses_a_skill_locked_in_the_store(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("demo", skill_md, locked=True))

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 409
    evolution.engine.derive_skill_simple.assert_not_awaited()


async def test_derive_refuses_a_skill_locked_in_its_file(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("demo", skill_md))
    skill_md.write_text(FILE_LOCKED, encoding="utf-8")

    response = await client.post(f"/api/v1/evolution/derive/{PAGE_ID}", json=DERIVE)

    assert response.status_code == 409
    evolution.engine.derive_skill_simple.assert_not_awaited()


async def test_fix_finds_the_row_keyed_by_name_from_the_page_id(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("demo", skill_md))

    response = await client.post(f"/api/v1/evolution/fix/{PAGE_ID}", json={"reason": "broken"})

    assert response.status_code == 200
    await until(lambda: evolution.queue.enqueue.await_count)
    assert evolution.queue.enqueue.await_args.args[0].skill_id == "demo"


@pytest.mark.parametrize("file_locked", [False, True], ids=["store-lock", "file-lock"])
async def test_fix_refuses_a_locked_skill_even_when_the_retry_is_forced(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace, file_locked: bool
) -> None:
    await store.save_skill(evolution_row("demo", skill_md, locked=not file_locked))
    if file_locked:
        skill_md.write_text(FILE_LOCKED, encoding="utf-8")

    response = await client.post("/api/v1/evolution/fix/demo", json={"reason": "broken", "force_retry": True})

    assert response.status_code == 409
    evolution.queue.enqueue.assert_not_awaited()


async def test_unlock_clears_the_row_keyed_by_name_and_the_file(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("demo", skill_md, locked=True))
    skill_md.write_text(FILE_LOCKED, encoding="utf-8")

    response = await client.post(f"/api/v1/skills/{PAGE_ID}/evolution-lock", params={"locked": "false"})

    assert response.status_code == 200
    assert store.is_evolution_locked("demo") is False
    assert "evolution-locked: false" in skill_md.read_text(encoding="utf-8")


async def test_lock_marks_every_row_of_the_skill(
    client: AsyncClient, store: SkillStore, skill_md: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("demo", skill_md))
    await store.save_skill(evolution_row(PAGE_ID, skill_md))

    response = await client.post(f"/api/v1/skills/{PAGE_ID}/evolution-lock", params={"locked": "true"})

    assert response.status_code == 200
    assert store.is_evolution_locked("demo") is True
    assert store.is_evolution_locked(PAGE_ID) is True
