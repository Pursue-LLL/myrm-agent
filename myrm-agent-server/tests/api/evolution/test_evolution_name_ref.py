"""
[INPUT]
- app.core.skills.store.service::skills_service (POS: local skill lookup by directory name or by a name the skill is known by)
- app.core.skills.creation.service::skill_creation_service (POS: primary local skills directory)
- tests.api.evolution.conftest (POS: shared store, integration and client wiring, and the real local scan of a skill directory)
[OUTPUT]
- Tests that /derive and /fix take a local skill's name as its reference even when the skill has no evolution row,
  and that the lookup by name never leaves the primary local skills directory, finds the skill by its directory name
  first and then by a name it is known by (the name in its SKILL.md or the one the agent runtime lists it under),
  chooses none of several skills that go by one name, skips a SKILL.md that cannot be read or that the scan rejects and
  a directory with a blank name, finds no skill for a name no
  directory can have, and does not turn an unreadable directory into a missing skill.
[POS]
The growth audit names a skill only by the name its draft carried, and most local skills (made in chat, placed by hand)
have no evolution row yet, so a name has to reach the Skills page skill itself: a locked skill is refused without being
given a row, an unlocked one gets a row keyed by its page id, and a row that already holds the skill's SKILL.md under
another key is the one evolved. Page skills come from the real local scan, so their ids, paths and locks are the product's.
"""

from __future__ import annotations

import errno
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from myrm_agent_harness.agent.skills.evolution import SkillStore

from app.core.skills.creation.service import skill_creation_service
from app.core.skills.store.service import skills_service
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
async def test_a_skill_directory_is_found_by_its_name_whatever_its_spelling(skills_root: Path, dir_name: str) -> None:
    write_skill(skills_root, dir_name)

    assert await skills_service.find_local_skill_dir(dir_name) == skills_root / dir_name


@pytest.mark.parametrize("name", ["..", "group/inner", ""])
async def test_a_name_that_is_not_one_directory_below_the_skills_directory_is_no_skill(skills_root: Path, name: str) -> None:
    (skills_root.parent / "SKILL.md").write_text(UNLOCKED, encoding="utf-8")
    write_skill(skills_root, "group/inner")
    (skills_root / "SKILL.md").write_text(UNLOCKED, encoding="utf-8")

    assert await skills_service.find_local_skill_dir(name) is None


@pytest.mark.parametrize("length", [256, 300])
async def test_a_name_longer_than_a_directory_name_can_be_is_no_skill(skills_root: Path, length: int) -> None:
    write_skill(skills_root, "demo")

    assert await skills_service.find_local_skill_dir("a" * length) is None


async def test_a_missing_skills_directory_has_no_skill(skills_root: Path) -> None:
    assert not skills_root.exists()

    assert await skills_service.find_local_skill_dir("demo") is None


@pytest.mark.parametrize("ref", ["report_builder_skill", "report-builder"], ids=["listed-name", "skill-md-name"])
async def test_a_skill_is_found_by_a_name_it_is_known_by_when_no_directory_has_that_name(skills_root: Path, ref: str) -> None:
    write_skill(skills_root, "rb", name="report-builder")
    write_skill(skills_root, "other", name="other-skill")

    assert await skills_service.find_local_skill_dir(ref) == skills_root / "rb"


async def test_a_skill_without_a_name_in_its_skill_md_is_known_by_its_directory_name(skills_root: Path) -> None:
    skill_md = skills_root / "report-builder" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\ndescription: Demo skill.\n---\n", encoding="utf-8")

    assert await skills_service.find_local_skill_dir("report_builder_skill") == skills_root / "report-builder"


async def test_a_directory_of_that_name_wins_over_a_skill_that_is_known_by_it(skills_root: Path) -> None:
    write_skill(skills_root, "demo", name="demo")
    write_skill(skills_root, "other", name="demo")

    assert await skills_service.find_local_skill_dir("demo") == skills_root / "demo"


async def test_skills_that_go_by_the_same_name_are_not_told_apart(skills_root: Path) -> None:
    write_skill(skills_root, "one", name="report-builder")
    write_skill(skills_root, "two", name="report_builder")

    assert await skills_service.find_local_skill_dir("report_builder_skill") is None


async def test_an_unreadable_skill_md_does_not_hide_the_other_skills(skills_root: Path) -> None:
    write_skill(skills_root, "good", name="report-builder")
    (skills_root / "broken").mkdir()
    (skills_root / "broken" / "SKILL.md").write_bytes(b"\xff\xfe\x00")

    assert await skills_service.find_local_skill_dir("report_builder_skill") == skills_root / "good"


async def test_a_skill_md_the_scan_rejects_does_not_hide_the_other_skills(skills_root: Path) -> None:
    write_skill(skills_root, "good", name="report-builder")
    (skills_root / "invalid").mkdir()
    (skills_root / "invalid" / "SKILL.md").write_text("A SKILL.md without a frontmatter.\n", encoding="utf-8")

    assert await skills_service.find_local_skill_dir("report_builder_skill") == skills_root / "good"


@pytest.mark.skipif(sys.platform == "win32", reason="Windows cannot create a directory whose name is blank")
async def test_a_directory_with_a_blank_name_does_not_hide_the_other_skills(skills_root: Path) -> None:
    write_skill(skills_root, "good", name="report-builder")
    (skills_root / " ").mkdir()
    (skills_root / " " / "SKILL.md").write_text("---\ndescription: Demo skill.\n---\n", encoding="utf-8")

    assert await skills_service.find_local_skill_dir("report_builder_skill") == skills_root / "good"


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


async def test_a_skill_md_that_cannot_be_opened_does_not_hide_the_other_skills(
    skills_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_skill(skills_root, "good", name="report-builder")
    write_skill(skills_root, "shut", name="other-skill")
    read_text = Path.read_text

    def read_text_unless_shut(self: Path, encoding: str | None = None, errors: str | None = None) -> str:
        if self.parent.name == "shut":
            raise PermissionError(errno.EACCES, "Permission denied", str(self))
        return read_text(self, encoding=encoding, errors=errors)

    with monkeypatch.context() as patched:
        patched.setattr(Path, "read_text", read_text_unless_shut)
        assert await skills_service.find_local_skill_dir("report_builder_skill") == skills_root / "good"


async def test_an_unreadable_skills_directory_is_an_error_and_not_a_missing_skill(
    skills_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_skill(skills_root, "demo", locked=True)

    def deny(self: Path, *, follow_symlinks: bool = True) -> bool:
        raise PermissionError(errno.EACCES, "Permission denied", str(self))

    with monkeypatch.context() as patched:
        patched.setattr(Path, "is_file", deny)
        with pytest.raises(PermissionError):
            await skills_service.find_local_skill_dir("demo")


async def test_an_unreadable_skills_directory_is_an_error_when_looking_for_a_known_name(
    skills_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_skill(skills_root, "rb", name="report-builder")

    def deny(self: Path) -> Iterator[Path]:
        raise PermissionError(errno.EACCES, "Permission denied", str(self))

    with monkeypatch.context() as patched:
        patched.setattr(Path, "iterdir", deny)
        with pytest.raises(PermissionError):
            await skills_service.find_local_skill_dir("report_builder_skill")


@pytest.mark.parametrize(("endpoint", "body"), ENDPOINTS)
async def test_a_locked_skill_named_by_the_name_the_agent_lists_it_under_is_refused(
    client: AsyncClient,
    store: SkillStore,
    skills_root: Path,
    evolution: SimpleNamespace,
    endpoint: str,
    body: dict[str, object],
) -> None:
    write_skill(skills_root, "report-builder", name="report-builder", locked=True)
    publish_pages(evolution, skills_root)

    response = await client.post(f"/api/v1/evolution/{endpoint}/report_builder_skill", json=body)

    assert response.status_code == 409
    assert store.get_active_skills() == []


@pytest.mark.parametrize(("endpoint", "body"), ENDPOINTS)
async def test_an_unlocked_skill_named_by_the_name_the_agent_lists_it_under_is_given_a_row(
    client: AsyncClient,
    store: SkillStore,
    skills_root: Path,
    evolution: SimpleNamespace,
    endpoint: str,
    body: dict[str, object],
) -> None:
    write_skill(skills_root, "report-builder", name="report-builder")
    page = publish_pages(evolution, skills_root)["report-builder"]

    response = await client.post(f"/api/v1/evolution/{endpoint}/report_builder_skill", json=body)

    assert response.status_code == 200
    await until(lambda: _evolved_row_ids(evolution, endpoint))
    assert _evolved_row_ids(evolution, endpoint) == [page.id]
