"""
[INPUT]
- app.core.skills.store.evolution_store::find_evolution_records (POS: evolution rows of one skill)
- tests.api.evolution.conftest (POS: shared store, integration and client wiring, and the real local scan of a skill directory)
[OUTPUT]
- Tests that a Skills page skill reaches the evolution rows that hold its own SKILL.md, whatever the row is named,
  and never another skill's row.
[POS]
Evolution rows are keyed by whoever wrote them (skill name, generated id, page id) and the skill's frontmatter name
can change, so neither the page id nor the name identifies a row. The lock toggle, /derive and /fix identify a row by
the SKILL.md it holds: a renamed skill keeps the row with its regression cases, and two skills sharing a name each
keep their own. Page skills come from the real local scan, so their ids, paths and locks are the product's.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from httpx import AsyncClient
from myrm_agent_harness.agent.skills.evolution import SkillStore

from tests.api.evolution.conftest import DERIVE, evolution_row, publish_pages, until, write_skill


def _derived_row_ids(evolution: SimpleNamespace) -> list[object]:
    return [call.kwargs["skill_id"] for call in evolution.engine.derive_skill_simple.await_args_list]


async def _derive_and_wait(client: AsyncClient, evolution: SimpleNamespace, skill_id: str, *, calls: int) -> None:
    response = await client.post(f"/api/v1/evolution/derive/{skill_id}", json=DERIVE)
    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count == calls)


async def test_a_renamed_skill_evolves_the_row_of_its_old_name(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    skill_md = write_skill(root, "demo")
    await store.save_skill(evolution_row("demo", skill_md))
    skill_md.write_text(skill_md.read_text(encoding="utf-8").replace("name: demo", "name: renamed"), encoding="utf-8")
    page = publish_pages(evolution, root)["demo"]
    assert page.name == "renamed"

    response = await client.post(f"/api/v1/evolution/derive/{page.id}", json=DERIVE)

    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert _derived_row_ids(evolution) == ["demo"]
    assert [record.skill_id for record in store.get_active_skills()] == ["demo"]


async def test_the_lock_toggle_reaches_the_row_of_a_renamed_skill(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    skill_md = write_skill(root, "demo", name="renamed", locked=True)
    await store.save_skill(evolution_row("demo", skill_md, locked=True))
    page = publish_pages(evolution, root)["demo"]

    response = await client.post(f"/api/v1/skills/{page.id}/evolution-lock", params={"locked": "false"})

    assert response.status_code == 200
    assert store.is_evolution_locked("demo") is False
    assert "evolution-locked: false" in skill_md.read_text(encoding="utf-8")


async def test_a_row_recorded_through_a_symlink_is_found(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    skill_md = write_skill(tmp_path / "real", "demo")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    await store.save_skill(evolution_row("demo", tmp_path / "link" / "demo" / "SKILL.md"))
    page = publish_pages(evolution, tmp_path / "link")["demo"]
    assert page.storage_path == str(skill_md.parent.resolve())

    response = await client.post(f"/api/v1/evolution/derive/{page.id}", json=DERIVE)

    assert response.status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert _derived_row_ids(evolution) == ["demo"]


async def test_skills_sharing_a_name_each_evolve_their_own_row(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    await store.save_skill(evolution_row("alpha-row", write_skill(root, "alpha")))
    await store.save_skill(evolution_row("beta-row", write_skill(root, "beta")))
    pages = publish_pages(evolution, root)

    await _derive_and_wait(client, evolution, pages["alpha"].id, calls=1)
    await _derive_and_wait(client, evolution, pages["beta"].id, calls=2)

    assert _derived_row_ids(evolution) == ["alpha-row", "beta-row"]
    assert sorted(record.skill_id for record in store.get_active_skills()) == ["alpha-row", "beta-row"]


async def test_the_lock_toggle_marks_only_the_rows_of_its_own_skill(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    await store.save_skill(evolution_row("alpha-row", write_skill(root, "alpha")))
    await store.save_skill(evolution_row("beta-row", write_skill(root, "beta")))
    pages = publish_pages(evolution, root)

    response = await client.post(f"/api/v1/skills/{pages['beta'].id}/evolution-lock", params={"locked": "true"})

    assert response.status_code == 200
    assert store.is_evolution_locked("beta-row") is True
    assert store.is_evolution_locked("alpha-row") is False


async def test_a_skill_made_in_chat_can_be_unlocked_optimized_and_locked_again(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    skill_md = write_skill(root, "demo", locked=True)
    page = publish_pages(evolution, root)["demo"]
    assert page.evolution_locked is True

    assert (await client.post(f"/api/v1/evolution/derive/{page.id}", json=DERIVE)).status_code == 409
    assert store.get_active_skills() == []

    unlocked = await client.post(f"/api/v1/skills/{page.id}/evolution-lock", params={"locked": "false"})
    assert unlocked.status_code == 200
    assert "evolution-locked: false" in skill_md.read_text(encoding="utf-8")

    assert (await client.post(f"/api/v1/evolution/derive/{page.id}", json=DERIVE)).status_code == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)
    assert _derived_row_ids(evolution) == [page.id]

    locked = await client.post(f"/api/v1/skills/{page.id}/evolution-lock", params={"locked": "true"})
    assert locked.status_code == 200
    assert store.is_evolution_locked(page.id) is True
    assert (await client.post(f"/api/v1/evolution/derive/{page.id}", json=DERIVE)).status_code == 409
    assert evolution.engine.derive_skill_simple.await_count == 1
