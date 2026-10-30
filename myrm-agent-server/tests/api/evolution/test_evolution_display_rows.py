"""
[INPUT]
- app.api.skills.converter::skill_to_response, skills_to_responses (POS: Skill to API response adapter that reads the skill's evolution state)
- tests.api.evolution.conftest (POS: shared store, integration and client wiring, and the real local scan of a skill directory)
[OUTPUT]
- Tests that the Skills page shows a local skill's lock and regression cases from the evolution row that holds its own
  SKILL.md, the row /derive and the lock toggle run on, and that a list request reads the store once.
[POS]
The page's lock state decides whether Optimize is offered, while /derive refuses by the row it runs on, so both must
pick the row alike: a renamed skill shows the lock of its old-named row, and two skills sharing a name never show each
other's lock or regression cases. A skill that is not local has no directory of its own and is shown by name.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from myrm_agent_harness.agent.skills.evolution import SkillStore

from tests.api.evolution.conftest import (
    DERIVE,
    PREBUILT_ID,
    evolution_row,
    publish_pages,
    until,
    write_skill,
)


async def _shown(client: AsyncClient, skill_id: str) -> dict[str, object]:
    response = await client.get(f"/api/v1/skills/{skill_id}")
    assert response.status_code == 200
    shown: dict[str, object] = response.json()
    return shown


async def _derive_status(client: AsyncClient, skill_id: str) -> int:
    return (await client.post(f"/api/v1/evolution/derive/{skill_id}", json=DERIVE)).status_code


async def test_a_renamed_skill_shows_the_lock_of_its_old_named_row(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    skill_md = write_skill(root, "demo")
    await store.save_skill(evolution_row("demo", skill_md, locked=True))
    skill_md.write_text(skill_md.read_text(encoding="utf-8").replace("name: demo", "name: renamed"), encoding="utf-8")
    page = publish_pages(evolution, root)["demo"]
    assert (page.name, page.evolution_locked) == ("renamed", False)

    assert (await _shown(client, page.id))["evolution_locked"] is True
    assert await _derive_status(client, page.id) == 409


async def test_locking_and_unlocking_one_skill_never_shows_in_the_one_sharing_its_name(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    await store.save_skill(evolution_row("alpha-row", write_skill(root, "alpha"), locked=True))
    await store.save_skill(evolution_row("beta-row", write_skill(root, "beta")))
    pages = publish_pages(evolution, root)

    async def lock_states() -> list[object]:
        return [(await _shown(client, pages[name].id))["evolution_locked"] for name in ("alpha", "beta")]

    assert await lock_states() == [True, False]
    await client.post(f"/api/v1/skills/{pages['beta'].id}/evolution-lock", params={"locked": "true"})
    assert await lock_states() == [True, True]
    await client.post(f"/api/v1/skills/{pages['beta'].id}/evolution-lock", params={"locked": "false"})
    assert await lock_states() == [True, False]
    assert await _derive_status(client, pages["beta"].id) == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)


async def test_a_skill_shows_the_regression_cases_of_its_own_row_only(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    case = {"id": "case-1", "prompt": "empty input"}
    await store.save_skill(replace(evolution_row("alpha-row", write_skill(root, "alpha")), eval_cases=[case]))
    await store.save_skill(evolution_row("beta-row", write_skill(root, "beta")))
    pages = publish_pages(evolution, root)

    assert (await _shown(client, pages["alpha"].id))["eval_cases"] == [case]
    assert (await _shown(client, pages["beta"].id))["eval_cases"] == []


async def test_a_row_that_holds_another_directory_is_not_shown(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    write_skill(root, "demo")
    await store.save_skill(evolution_row("demo", write_skill(tmp_path / "elsewhere", "demo"), locked=True))
    page = publish_pages(evolution, root)["demo"]

    assert (await _shown(client, page.id))["evolution_locked"] is False


@pytest.mark.parametrize("locked", [True, False])
async def test_a_skill_without_a_row_shows_the_lock_in_its_file(
    client: AsyncClient, tmp_path: Path, evolution: SimpleNamespace, locked: bool
) -> None:
    root = tmp_path / "skills"
    write_skill(root, "demo", locked=locked)
    page = publish_pages(evolution, root)["demo"]

    assert (await _shown(client, page.id))["evolution_locked"] is locked


async def test_the_row_keyed_by_the_page_id_is_the_one_shown(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    skill_md = write_skill(root, "demo")
    page = publish_pages(evolution, root)["demo"]
    await store.save_skill(evolution_row(page.id, skill_md))
    await store.save_skill(evolution_row("newer", skill_md, locked=True))

    assert (await _shown(client, page.id))["evolution_locked"] is False
    assert await _derive_status(client, page.id) == 200
    await until(lambda: evolution.engine.derive_skill_simple.await_count)


async def test_a_skill_that_is_not_local_is_shown_by_name(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    await store.save_skill(evolution_row("row", write_skill(tmp_path / "elsewhere", "demo"), locked=True))

    assert (await _shown(client, PREBUILT_ID))["evolution_locked"] is True


async def test_a_list_request_reads_the_evolution_rows_once(
    client: AsyncClient, store: SkillStore, tmp_path: Path, evolution: SimpleNamespace
) -> None:
    root = tmp_path / "skills"
    await store.save_skill(evolution_row("alpha-row", write_skill(root, "alpha", name="alpha"), name="alpha", locked=True))
    for name in ("beta", "gamma"):
        write_skill(root, name, name=name)
    pages = publish_pages(evolution, root)

    with (
        patch("app.core.skills.store.service.skills_service.list_skills", new=AsyncMock(return_value=list(pages.values()))),
        patch.object(store, "get_active_skills", wraps=store.get_active_skills) as scan,
    ):
        response = await client.get("/api/v1/skills/")

    assert response.status_code == 200
    shown = {Path(item["storage_path"]).name: item["evolution_locked"] for item in response.json()["skills"]}
    assert shown == {"alpha": True, "beta": False, "gamma": False}
    assert scan.call_count == 1
