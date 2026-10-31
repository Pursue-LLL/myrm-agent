"""
[INPUT]
- app.core.skills.store.service::skills_service (POS: local skill lookup by directory name)
- app.core.skills.creation.service::skill_creation_service (POS: primary local skills directory)
- tests.api.evolution.conftest (POS: shared store, integration and client wiring, and the real local scan of a skill directory)
[OUTPUT]
- Tests that /derive and /fix take a local skill's name as its reference even when the skill has no evolution row,
  and that the lookup by name never leaves the primary local skills directory, finds no skill for a name no directory
  can have, and does not turn an unreadable directory into a missing skill.
[POS]
The growth audit names a skill only by the name its draft carried, and most local skills (made in chat, placed by hand)
have no evolution row yet, so a name has to reach the Skills page skill itself: a locked skill is refused without being
given a row, an unlocked one gets a row keyed by its page id, and a row that already holds the skill's SKILL.md under
another key is the one evolved. Page skills come from the real local scan, so their ids, paths and locks are the product's.
"""

from __future__ import annotations

import errno
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from myrm_agent_harness.agent.skills.evolution import SkillStore

from app.core.skills.creation.service import skill_creation_service
from app.core.skills.models import Skill
from app.core.skills.providers.local import compute_local_skill_id
from app.core.skills.store.service import skills_service
from app.core.storage.types import SkillType
from tests.api.evolution.conftest import DERIVE, UNLOCKED, evolution_row, publish_pages, until, write_skill

FIX = {"reason": "The draft's description.", "force_retry": True}
ENDPOINTS = [pytest.param("derive", DERIVE, id="derive"), pytest.param("fix", FIX, id="fix")]


@pytest.fixture
def skills_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The primary local skills directory, where a skill is found by the name of its directory."""
    root = tmp_path / "skills"
    monkeypatch.setattr(skill_creation_service, "base_path", root)
    return root


def _evolved_row_ids(evolution: SimpleNamespace, endpoint: str) -> list[object]:
    if endpoint == "derive":
        return [call.kwargs["skill_id"] for call in evolution.engine.derive_skill_simple.await_args_list]
    return [call.args[0].skill_id for call in evolution.queue.enqueue.await_args_list]


def _known_page(evolution: SimpleNamespace, directory: Path) -> Skill:
    """A page skill of ``directory`` made known to the page service, without scanning its neighbours."""
    page = Skill(
        id=compute_local_skill_id(directory),
        type=SkillType.LOCAL,
        name=directory.name,
        description="Demo skill.",
        storage_path=str(directory),
    )
    evolution.pages[page.id] = page
    return page


@pytest.mark.parametrize(("endpoint", "body"), ENDPOINTS)
async def test_a_locked_skill_named_without_a_row_is_refused_and_given_none(
    client: AsyncClient,
    store: SkillStore,
    skills_root: Path,
    evolution: SimpleNamespace,
    endpoint: str,
    body: dict[str, object],
) -> None:
    write_skill(skills_root, "demo", locked=True)
    publish_pages(evolution, skills_root)

    response = await client.post(f"/api/v1/evolution/{endpoint}/demo", json=body)

    assert response.status_code == 409
    assert store.get_active_skills() == []


@pytest.mark.parametrize(("endpoint", "body"), ENDPOINTS)
async def test_an_unlocked_skill_named_without_a_row_is_given_one_keyed_by_its_page_id(
    client: AsyncClient,
    store: SkillStore,
    skills_root: Path,
    evolution: SimpleNamespace,
    endpoint: str,
    body: dict[str, object],
) -> None:
    write_skill(skills_root, "demo")
    page = publish_pages(evolution, skills_root)["demo"]

    response = await client.post(f"/api/v1/evolution/{endpoint}/demo", json=body)

    assert response.status_code == 200
    await until(lambda: _evolved_row_ids(evolution, endpoint))
    assert _evolved_row_ids(evolution, endpoint) == [page.id]
    assert [record.skill_id for record in store.get_active_skills()] == [page.id]


@pytest.mark.parametrize(("endpoint", "body"), ENDPOINTS)
async def test_a_name_reaches_the_row_that_holds_the_skill_under_another_key(
    client: AsyncClient,
    store: SkillStore,
    skills_root: Path,
    evolution: SimpleNamespace,
    endpoint: str,
    body: dict[str, object],
) -> None:
    skill_md = write_skill(skills_root, "demo")
    await store.save_skill(evolution_row("alias", skill_md, name="renamed"))
    publish_pages(evolution, skills_root)

    response = await client.post(f"/api/v1/evolution/{endpoint}/demo", json=body)

    assert response.status_code == 200
    await until(lambda: _evolved_row_ids(evolution, endpoint))
    assert _evolved_row_ids(evolution, endpoint) == ["alias"]
    assert [record.skill_id for record in store.get_active_skills()] == ["alias"]


@pytest.mark.parametrize(("endpoint", "body"), ENDPOINTS)
async def test_a_row_of_that_name_is_still_the_one_a_name_reaches(
    client: AsyncClient,
    store: SkillStore,
    skills_root: Path,
    skill_md: Path,
    evolution: SimpleNamespace,
    endpoint: str,
    body: dict[str, object],
) -> None:
    await store.save_skill(evolution_row("row-1", skill_md))
    write_skill(skills_root, "demo")
    publish_pages(evolution, skills_root)

    response = await client.post(f"/api/v1/evolution/{endpoint}/demo", json=body)

    assert response.status_code == 200
    await until(lambda: _evolved_row_ids(evolution, endpoint))
    assert _evolved_row_ids(evolution, endpoint) == ["row-1"]
    assert [record.skill_id for record in store.get_active_skills()] == ["row-1"]


async def test_a_name_with_no_skill_directory_is_not_found(
    client: AsyncClient, store: SkillStore, skills_root: Path, evolution: SimpleNamespace
) -> None:
    (skills_root / "empty").mkdir(parents=True)

    for name in ("ghost", "empty"):
        response = await client.post(f"/api/v1/evolution/derive/{name}", json=DERIVE)
        assert response.status_code == 404
    assert store.get_active_skills() == []


@pytest.mark.parametrize("dir_name", ["demo", "My Skill", "skill.v2"])
async def test_a_skill_directory_is_found_by_its_name_whatever_its_spelling(
    skills_root: Path, evolution: SimpleNamespace, dir_name: str
) -> None:
    write_skill(skills_root, dir_name)
    page = _known_page(evolution, skills_root / dir_name)

    assert await skills_service.get_local_skill_by_dir_name(dir_name) == page


@pytest.mark.parametrize("name", ["..", "group/inner", ""])
async def test_a_name_that_is_not_one_directory_below_the_skills_directory_is_no_skill(
    skills_root: Path, evolution: SimpleNamespace, name: str
) -> None:
    (skills_root.parent / "SKILL.md").write_text(UNLOCKED, encoding="utf-8")
    write_skill(skills_root, "group/inner")
    (skills_root / "SKILL.md").write_text(UNLOCKED, encoding="utf-8")
    for directory in (skills_root.parent, skills_root, skills_root / "group" / "inner"):
        _known_page(evolution, directory)

    assert await skills_service.get_local_skill_by_dir_name(name) is None


@pytest.mark.parametrize("length", [256, 300])
async def test_a_name_longer_than_a_directory_name_can_be_is_no_skill(
    skills_root: Path, evolution: SimpleNamespace, length: int
) -> None:
    write_skill(skills_root, "demo")

    assert await skills_service.get_local_skill_by_dir_name("a" * length) is None


@pytest.mark.parametrize(("endpoint", "body"), ENDPOINTS)
async def test_a_reference_longer_than_a_directory_name_can_be_is_not_found(
    client: AsyncClient,
    store: SkillStore,
    skills_root: Path,
    evolution: SimpleNamespace,
    endpoint: str,
    body: dict[str, object],
) -> None:
    write_skill(skills_root, "demo")
    publish_pages(evolution, skills_root)

    response = await client.post(f"/api/v1/evolution/{endpoint}/{'a' * 300}", json=body)

    assert response.status_code == 404
    assert store.get_active_skills() == []


async def test_an_unreadable_skills_directory_is_an_error_and_not_a_missing_skill(
    skills_root: Path, evolution: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_skill(skills_root, "demo", locked=True)

    def deny(self: Path, *, follow_symlinks: bool = True) -> bool:
        raise PermissionError(errno.EACCES, "Permission denied", str(self))

    with monkeypatch.context() as patched:
        patched.setattr(Path, "is_file", deny)
        with pytest.raises(PermissionError):
            await skills_service.get_local_skill_by_dir_name("demo")
