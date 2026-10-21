"""The curator scan tells authored skills from installed ones using real skill directories."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.agent.skills.market.helpers import write_origin

from app.core.skills import models
from app.core.skills.curator.local_skills import scan_local_skills


def _write_skill(root: Path, name: str, *, from_market: bool = False) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Skill {name}\n---\nBody.\n", encoding="utf-8")
    if from_market:
        write_origin(skill_dir, source="registry", skill_id=f"registry::{name}", version="1.0.0")


@pytest.fixture
def own_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Primary root plus one other tool's root, in the order the app configures them."""
    own = tmp_path / "myrm-skills"
    other_tool = tmp_path / "other-tool-skills"
    own.mkdir()
    other_tool.mkdir()
    monkeypatch.setattr(models, "DEFAULT_LOCAL_SKILL_PATHS", [str(own), str(other_tool)])
    return own


async def test_authored_skill_in_primary_root_is_not_installed(own_root: Path) -> None:
    _write_skill(own_root, "my-notes")

    scan = await scan_local_skills()

    assert [s.name for s in scan.skills] == ["my-notes"]
    assert scan.installed_names == frozenset()


async def test_market_install_in_primary_root_is_installed(own_root: Path) -> None:
    _write_skill(own_root, "my-notes")
    _write_skill(own_root, "from-store", from_market=True)

    scan = await scan_local_skills()

    assert {s.name for s in scan.skills} == {"my-notes", "from-store"}
    assert scan.installed_names == {"from-store"}


async def test_skill_in_another_tools_root_is_installed(own_root: Path, tmp_path: Path) -> None:
    _write_skill(own_root, "my-notes")
    _write_skill(tmp_path / "other-tool-skills", "their-skill")

    scan = await scan_local_skills()

    assert {s.name for s in scan.skills} == {"my-notes", "their-skill"}
    assert scan.installed_names == {"their-skill"}


async def test_missing_primary_root_does_not_turn_another_root_into_the_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_tool = tmp_path / "other-tool-skills"
    other_tool.mkdir()
    _write_skill(other_tool, "their-skill")
    monkeypatch.setattr(models, "DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path / "not-created-yet"), str(other_tool)])

    scan = await scan_local_skills()

    assert scan.installed_names == {"their-skill"}


async def test_no_roots_means_nothing_to_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(models, "DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path / "absent")])

    scan = await scan_local_skills()

    assert scan.skills == []
    assert scan.installed_names == frozenset()
