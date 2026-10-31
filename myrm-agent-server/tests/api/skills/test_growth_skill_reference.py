"""
[INPUT]
- app.services.skills.growth.lifecycle::process_skill_review_result (POS: unified entry for a background review result)
- app.core.skills.runtime_metadata::skill_to_runtime_metadata (POS: the name a skill is listed under for the agent runtime)
- app.api.skills.drafts::approve_skill_draft (POS: approval of a held draft)
- app.core.skills.store.local_lookup::approval_writes_into, _as_listed (POS: whether approving a draft under a name writes into the directory of the skill it names; a directory under the name the skills directory lists it by)
- tests.api.skills.conftest (POS: primary local skills directory moved to a temporary one, real local scan)
[OUTPUT]
- Tests that a review result finds the skill it names whether it carries the skill's directory name, its listed name
  or the name from its SKILL.md, whatever that name's spelling, that the lock and the approval act on that skill,
  that two skills a name cannot tell apart are not guessed between, that on a volume that does not tell spellings apart
  a name spelled unlike the directory's still finds the skill and an approved draft under it acts on that skill, that
  on any volume a new skill is recorded under the directory's name exactly when approving it writes into that
  directory (judged by the name the approval writes, so a name it rewrites is judged by that), that a skill removed
  while the skills directory is being listed keeps the name it was looked up by, and that a name no directory can
  have is recorded and not dropped.
[POS]
The reviewer is shown the names the agent runtime lists skills under (``normalize_skill_name``), while the draft
pipeline keeps, locks and patches skills by directory. The names are built by the product's own adapter and the skills
come from the real local scan, so a mismatch between the two is what these tests would catch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api.skills.drafts import ApproveDraftRequest, approve_skill_draft
from app.core.skills.providers.local import compute_local_skill_id
from app.core.skills.runtime_metadata import skill_to_runtime_metadata
from app.core.skills.store.local_lookup import _as_listed, approval_writes_into
from app.core.skills.store.service import skills_service
from app.services.skills.growth.case_types import SkillGrowthCaseDetailRead, SkillGrowthCaseStatus
from app.services.skills.growth.lifecycle import process_skill_review_result
from app.services.skills.growth.queries import get_skill_growth_case_detail

PATCH = "<<<<<<< SEARCH\n1. Old behavior\n=======\n1. New behavior\n>>>>>>> REPLACE"


def _write_skill(root: Path, dir_name: str, *, name: str | None = None, locked: bool = False) -> Path:
    directory = root / dir_name
    directory.mkdir(parents=True)
    lock = "evolution_locked: true\n" if locked else ""
    (directory / "SKILL.md").write_text(
        f"---\nname: {name or dir_name}\ndescription: Build the weekly report.\n{lock}---\n\n## Steps\n1. Old behavior\n",
        encoding="utf-8",
    )
    return directory


def _write_skill_on_case_insensitive_volume(root: Path, dir_name: str, *, locked: bool = False) -> Path:
    """A skill whose directory a name spelled in lower case opens too; skips on a volume that tells the spellings apart."""
    directory = _write_skill(root, dir_name, locked=locked)
    if not (root / dir_name.lower()).exists():
        pytest.skip("the volume tells names that differ in case apart")
    return directory


async def _listed_name(directory: Path) -> str:
    """The name the agent runtime lists the skill in ``directory`` under, built by the product's own adapter."""
    page = await skills_service.get_skill(compute_local_skill_id(directory))
    assert page is not None
    return skill_to_runtime_metadata(page).name


def _review(kind: str, skill_name: str) -> dict[str, object]:
    return {
        "has_value": True,
        "user_id": "growth_user_reference",
        "type": kind,
        "skill_name": skill_name,
        "skill_description": "Build the weekly report.",
        "trigger_condition": "When the user asks for the weekly report.",
        "skill_steps": "1. Build the report.",
        "content": PATCH if kind == "skill_patch" else "1. Build the report.",
    }


def _skill_dirs(root: Path) -> list[str]:
    return sorted(path.name for path in root.iterdir() if path.is_dir())


async def _recorded(result: dict[str, object]) -> SkillGrowthCaseDetailRead:
    draft = await process_skill_review_result(result)
    assert draft is not None
    detail = await get_skill_growth_case_detail(f"draft:{draft.id}")
    assert detail is not None
    return detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dir_name", "name"),
    [
        pytest.param("report-builder", None, id="hyphenated-directory"),
        pytest.param("plain", None, id="plain-directory"),
        pytest.param("plain", "MyTool", id="mixed-case-name"),
        pytest.param("plain", '"quoted-name"', id="quoted-name"),
        pytest.param("plain", "a" * 70, id="name-over-64-characters"),
    ],
)
async def test_a_patch_for_a_locked_skill_is_blocked_under_the_name_the_reviewer_saw(
    mock_local_skills_dir: Path, dir_name: str, name: str | None
) -> None:
    directory = _write_skill(mock_local_skills_dir, dir_name, name=name, locked=True)
    seen = await _listed_name(directory)
    assert seen != dir_name

    detail = await _recorded(_review("skill_patch", seen))

    assert detail.status == SkillGrowthCaseStatus.BLOCKED_LOCKED
    assert detail.reason_code == "evolution_locked"
    assert detail.skill_name == dir_name


@pytest.mark.asyncio
async def test_a_patch_under_the_name_the_reviewer_saw_lands_on_that_skill_when_approved(
    mock_local_skills_dir: Path,
) -> None:
    directory = _write_skill(mock_local_skills_dir, "report-builder")
    seen = await _listed_name(directory)

    detail = await _recorded(_review("skill_patch", seen))

    assert detail.status == SkillGrowthCaseStatus.PENDING_REVIEW
    assert detail.skill_name == "report-builder"
    approved = await approve_skill_draft(detail.id.removeprefix("draft:"), ApproveDraftRequest())
    assert approved["materialized"] is True
    assert "1. New behavior" in (directory / "SKILL.md").read_text(encoding="utf-8")
    assert _skill_dirs(mock_local_skills_dir) == ["report-builder"]


@pytest.mark.asyncio
@pytest.mark.parametrize("named", ["report_builder_skill", "report-builder"], ids=["listed-name", "skill-md-name"])
async def test_a_skill_whose_directory_is_not_its_name_is_found_by_either_name(mock_local_skills_dir: Path, named: str) -> None:
    directory = _write_skill(mock_local_skills_dir, "rb", name="report-builder", locked=True)
    assert await _listed_name(directory) == "report_builder_skill"

    detail = await _recorded(_review("skill_patch", named))

    assert detail.status == SkillGrowthCaseStatus.BLOCKED_LOCKED
    assert detail.skill_name == "rb"


@pytest.mark.asyncio
async def test_a_skill_kept_behind_a_link_goes_by_the_name_of_its_entry(mock_local_skills_dir: Path, tmp_path: Path) -> None:
    target = _write_skill(tmp_path / "elsewhere", "actual-dir", name="report-builder", locked=True)
    try:
        (mock_local_skills_dir / "linked").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("the file system does not allow links")

    detail = await _recorded(_review("skill_patch", "report_builder_skill"))

    assert detail.status == SkillGrowthCaseStatus.BLOCKED_LOCKED
    assert detail.skill_name == "linked"


@pytest.mark.asyncio
async def test_skills_a_name_cannot_tell_apart_are_not_guessed_between(mock_local_skills_dir: Path) -> None:
    first = _write_skill(mock_local_skills_dir, "foo-bar", locked=True)
    second = _write_skill(mock_local_skills_dir, "foo_bar")
    assert await _listed_name(first) == await _listed_name(second) == "foo_bar_skill"

    ambiguous = await _recorded(_review("skill_patch", "foo_bar_skill"))
    exact = await _recorded(_review("skill_patch", "foo-bar"))

    assert ambiguous.status == SkillGrowthCaseStatus.PENDING_REVIEW
    assert ambiguous.skill_name == "foo_bar_skill"
    assert exact.status == SkillGrowthCaseStatus.BLOCKED_LOCKED


@pytest.mark.asyncio
async def test_a_new_skill_under_the_listed_name_of_an_existing_one_is_held_and_not_created_beside_it(
    mock_local_skills_dir: Path,
) -> None:
    directory = _write_skill(mock_local_skills_dir, "report-builder")
    seen = await _listed_name(directory)

    detail = await _recorded(_review("skill_draft", seen))

    assert detail.status == SkillGrowthCaseStatus.PENDING_REVIEW
    assert detail.skill_name == seen
    assert _skill_dirs(mock_local_skills_dir) == ["report-builder"]


@pytest.mark.asyncio
@pytest.mark.parametrize("result_type", ["skill_patch", "skill_draft"])
async def test_a_locked_skill_is_blocked_under_a_spelling_its_directory_name_does_not_have(
    mock_local_skills_dir: Path, result_type: str
) -> None:
    directory = _write_skill_on_case_insensitive_volume(mock_local_skills_dir, "Report-Builder", locked=True)
    before = (directory / "SKILL.md").read_bytes()

    detail = await _recorded(_review(result_type, "report-builder"))

    assert detail.status == SkillGrowthCaseStatus.BLOCKED_LOCKED
    assert detail.skill_name == "Report-Builder"
    assert (directory / "SKILL.md").read_bytes() == before
    assert _skill_dirs(mock_local_skills_dir) == ["Report-Builder"]


@pytest.mark.asyncio
async def test_a_dangling_link_beside_a_skill_does_not_stop_it_being_found_under_another_spelling(
    mock_local_skills_dir: Path,
) -> None:
    _write_skill_on_case_insensitive_volume(mock_local_skills_dir, "Report-Builder", locked=True)
    try:
        (mock_local_skills_dir / "0-gone").symlink_to(mock_local_skills_dir / "missing", target_is_directory=True)
    except OSError:
        pytest.skip("the file system does not allow links")

    detail = await _recorded(_review("skill_patch", "report-builder"))

    assert detail.status == SkillGrowthCaseStatus.BLOCKED_LOCKED
    assert detail.skill_name == "Report-Builder"


@pytest.mark.asyncio
async def test_a_new_skill_spelled_unlike_an_existing_one_is_held_and_not_written_over_it(
    mock_local_skills_dir: Path,
) -> None:
    directory = _write_skill_on_case_insensitive_volume(mock_local_skills_dir, "Report-Builder")
    before = (directory / "SKILL.md").read_bytes()

    detail = await _recorded(_review("skill_draft", "report-builder"))

    assert detail.status == SkillGrowthCaseStatus.PENDING_REVIEW
    assert (directory / "SKILL.md").read_bytes() == before
    assert _skill_dirs(mock_local_skills_dir) == ["Report-Builder"]


@pytest.mark.asyncio
async def test_approving_a_new_skill_spelled_unlike_an_existing_one_acts_on_the_skill_that_is_there(
    mock_local_skills_dir: Path,
) -> None:
    directory = _write_skill_on_case_insensitive_volume(mock_local_skills_dir, "Report-Builder")
    detail = await _recorded(_review("skill_draft", "report-builder"))

    approved = await approve_skill_draft(detail.id.removeprefix("draft:"), ApproveDraftRequest())

    assert approved["materialized"] is True
    assert approved["skill_id"] == compute_local_skill_id(directory)
    assert _skill_dirs(mock_local_skills_dir) == ["Report-Builder"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dir_name", "name", "written_over"),
    [
        pytest.param("report-builder", "Report-Builder", None, id="capitalised"),
        pytest.param("report-builder", "Report Builder", None, id="spaced-and-capitalised"),
        pytest.param("report-builder", "Report-Builder.", None, id="capitalised-with-a-full-stop"),
        pytest.param("report-builder", "report builder", True, id="spaced"),
        pytest.param("report-builder", "report-builder-", True, id="with-a-trailing-hyphen"),
        pytest.param("skill-k", "skill-\u212a", False, id="kelvin-sign-for-k"),
        pytest.param("report-builder", "../{root}/report-builder", False, id="path-back-to-the-directory"),
    ],
)
async def test_a_new_skill_is_recorded_under_the_directory_name_exactly_when_approving_it_writes_into_that_directory(
    mock_local_skills_dir: Path, dir_name: str, name: str, written_over: bool | None
) -> None:
    """The existing skill is called ``name`` in its SKILL.md, so the review finds it.

    ``written_over`` is ``None`` where the volume decides: the directory is then written into exactly when the volume
    does not tell spellings of its name apart.
    """
    name = name.replace("{root}", mock_local_skills_dir.name)
    directory = _write_skill(mock_local_skills_dir, dir_name, name=name)
    before = (directory / "SKILL.md").read_bytes()

    detail = await _recorded(_review("skill_draft", name))
    approved = await approve_skill_draft(detail.id.removeprefix("draft:"), ApproveDraftRequest())

    assert detail.status == SkillGrowthCaseStatus.PENDING_REVIEW
    assert approved["materialized"] is True
    rewritten = (directory / "SKILL.md").read_bytes() != before
    assert (approved["skill_id"] == compute_local_skill_id(directory)) is rewritten
    assert (detail.skill_name == directory.name) is rewritten
    assert rewritten is (written_over if written_over is not None else (mock_local_skills_dir / dir_name.upper()).exists())


@pytest.mark.parametrize(
    ("dir_name", "name", "writes_into"),
    [
        pytest.param("report-builder", "report-builder", True, id="its-own-name"),
        pytest.param("report-builder", "report builder", True, id="spaced"),
        pytest.param("report-builder", "report-builder.", True, id="with-a-full-stop"),
        pytest.param("report-builder", "  report-builder  ", True, id="padded"),
        pytest.param("report-builder", "report-builder-", True, id="with-a-trailing-hyphen"),
        pytest.param("report-builder", "report\0builder", True, id="holding-a-nul"),
        pytest.param("report-builder", "another-directory", False, id="another-directory"),
        pytest.param("report-builder", "nowhere", False, id="no-entry"),
        pytest.param("skill-k", "skill-\u212a", False, id="kelvin-sign-for-k"),
        pytest.param("skill-s", "skill-\u017f", False, id="long-s-for-s"),
        pytest.param("report-builder", "../{root}/report-builder", False, id="path-back-to-the-directory"),
        pytest.param("report-builder", "{directory}", False, id="absolute-path-of-the-directory"),
    ],
)
def test_approving_a_draft_writes_into_a_skill_directory_only_when_its_cleansed_name_resolves_to_it(
    mock_local_skills_dir: Path, dir_name: str, name: str, writes_into: bool
) -> None:
    directory = _write_skill(mock_local_skills_dir, dir_name)
    (mock_local_skills_dir / "another-directory").mkdir()
    name = name.replace("{root}", mock_local_skills_dir.name).replace("{directory}", str(directory))

    assert approval_writes_into(directory, name) is writes_into


def test_a_skill_removed_while_the_skills_directory_is_listed_keeps_the_name_it_was_looked_up_by(
    mock_local_skills_dir: Path,
) -> None:
    removed = mock_local_skills_dir / "Report-Builder"
    (mock_local_skills_dir / "another-directory").mkdir()

    assert _as_listed(mock_local_skills_dir, removed) == removed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result_type", "reason_code"), [("skill_patch", None), ("skill_draft", "apply_failed")], ids=["patch", "draft"]
)
async def test_a_skill_name_longer_than_a_directory_name_can_be_is_recorded_not_dropped(
    mock_local_skills_dir: Path, result_type: str, reason_code: str | None
) -> None:
    detail = await _recorded(_review(result_type, "a" * 300))

    assert detail.status == SkillGrowthCaseStatus.PENDING_REVIEW
    assert detail.reason_code == reason_code
    assert _skill_dirs(mock_local_skills_dir) == []
