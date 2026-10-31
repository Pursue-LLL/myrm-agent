"""
[INPUT]
- app.api.skills.test_fixtures::(seed_growth_skill, seed_review_result, cleanup_growth_skills, request models) (POS: Dev-only skills fixture router for Chrome E2E (prebuilt catalog, skill-manage and upstream-update seeds, growth drafts); gated by is_local_mode())
- app.services.skills.growth.lifecycle::process_skill_review_result (POS: Skill growth lifecycle orchestration)
[OUTPUT]
- Tests that the three fixture routes answer 404 outside local mode, that a directory name outside one path component
  is refused before anything is written or removed, that seeding never overwrites an existing directory, that cleanup
  removes only real directories directly below the skills directory, and that a review result reaches the production
  lifecycle with the agent and the skill name the test chose.
[POS]
The cleanup route deletes directories, so its limits are pinned here instead of being left to the Chrome E2E that uses it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.api.skills.test_fixtures as fixtures
from app.core.skills.providers.local import compute_local_skill_id

_SEED = fixtures.SeedGrowthSkillRequest(dir_name="report-builder", skill_name="Report-Builder", marker="step-marker")


@pytest.fixture
def skills_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "skills"
    directory.mkdir()
    monkeypatch.setattr(fixtures, "LOCAL_SKILLS_DIR", directory)
    monkeypatch.setattr(fixtures, "is_local_mode", lambda: True)
    return directory


@pytest.mark.parametrize(
    "call",
    [
        lambda: fixtures.seed_growth_skill(_SEED),
        lambda: fixtures.seed_review_result(
            fixtures.SeedReviewResultRequest(skill_name="Report-Builder", agent_id="agent-1", marker="step-marker")
        ),
        lambda: fixtures.cleanup_growth_skills(fixtures.CleanupGrowthSkillsRequest(dir_names=["report-builder"])),
    ],
    ids=["seed-growth-skill", "seed-review-result", "cleanup-growth-skills"],
)
async def test_the_routes_do_not_exist_outside_local_mode(
    skills_dir: Path, monkeypatch: pytest.MonkeyPatch, call: Callable[[], Awaitable[object]]
) -> None:
    (skills_dir / "report-builder").mkdir()
    monkeypatch.setattr(fixtures, "is_local_mode", lambda: False)

    with pytest.raises(HTTPException) as refused:
        await call()

    assert refused.value.status_code == 404
    assert (skills_dir / "report-builder").is_dir()


@pytest.mark.parametrize("dir_name", ["../escape", "a/b", ".hidden", "", "-leading-hyphen", "x" * 64, "name with space"])
def test_a_directory_name_that_is_not_one_path_component_is_refused(dir_name: str) -> None:
    with pytest.raises(ValidationError):
        fixtures.SeedGrowthSkillRequest(dir_name=dir_name, skill_name="Report-Builder", marker="step-marker")
    with pytest.raises(ValidationError):
        fixtures.CleanupGrowthSkillsRequest(dir_names=[dir_name])


async def test_seeding_writes_a_skill_the_page_id_and_the_volume_report_describe(skills_dir: Path) -> None:
    seeded = await fixtures.seed_growth_skill(_SEED)

    directory = skills_dir / "report-builder"
    skill_md = (directory / "SKILL.md").read_text(encoding="utf-8")
    assert "name: Report-Builder\n" in skill_md and "1. step-marker" in skill_md
    assert seeded == {
        "skill_id": compute_local_skill_id(directory),
        "volume_ignores_case": (skills_dir / "REPORT-BUILDER").exists(),
    }


async def test_seeding_over_an_existing_directory_is_refused_and_leaves_it_alone(skills_dir: Path) -> None:
    existing = skills_dir / "report-builder"
    existing.mkdir()
    (existing / "SKILL.md").write_text("kept", encoding="utf-8")

    with pytest.raises(HTTPException) as refused:
        await fixtures.seed_growth_skill(_SEED)

    assert refused.value.status_code == 409
    assert (existing / "SKILL.md").read_text(encoding="utf-8") == "kept"


async def test_cleanup_removes_only_real_directories_directly_below_the_skills_directory(
    skills_dir: Path, tmp_path: Path
) -> None:
    (skills_dir / "mine").mkdir()
    (skills_dir / "mine" / "SKILL.md").write_text("x", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    (skills_dir / "linked").symlink_to(outside, target_is_directory=True)
    (skills_dir / "plain-file").write_text("keep", encoding="utf-8")

    result = await fixtures.cleanup_growth_skills(
        fixtures.CleanupGrowthSkillsRequest(dir_names=["mine", "linked", "plain-file", "absent"])
    )

    assert result == {"removed": ["mine"]}
    assert not (skills_dir / "mine").exists()
    assert (skills_dir / "linked").is_symlink() and (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert (skills_dir / "plain-file").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(("draft", "recorded"), [(object(), True), (None, False)])
async def test_a_review_result_reaches_the_production_lifecycle_as_a_new_skill_draft(
    skills_dir: Path, monkeypatch: pytest.MonkeyPatch, draft: object | None, recorded: bool
) -> None:
    received: list[dict[str, object]] = []

    async def lifecycle(result: dict[str, object]) -> object | None:
        received.append(result)
        return draft

    monkeypatch.setattr("app.services.skills.growth.lifecycle.process_skill_review_result", lifecycle)

    answer = await fixtures.seed_review_result(
        fixtures.SeedReviewResultRequest(skill_name="Report-Builder", agent_id="agent-1", marker="step-marker")
    )

    assert answer == {"recorded": recorded}
    (result,) = received
    assert result["type"] == "skill_draft" and result["has_value"] is True
    assert result["agent_id"] == "agent-1" and result["skill_name"] == "Report-Builder"
    assert result["skill_steps"] == "1. step-marker"
