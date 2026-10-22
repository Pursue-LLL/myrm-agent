"""The doctor reads the same skill roots as the sweep, using real skill directories."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig

from app.core.skills import models
from app.core.skills.curator import service


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Skill {name}\n---\nBody.\n", encoding="utf-8")


@pytest.fixture
def two_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Primary root plus one other tool's root, in the order the app configures them."""
    own = tmp_path / "myrm-skills"
    other_tool = tmp_path / "other-tool-skills"
    own.mkdir()
    other_tool.mkdir()
    monkeypatch.setattr(models, "DEFAULT_LOCAL_SKILL_PATHS", [str(own), str(other_tool)])
    monkeypatch.setattr(service, "_curator_config", CuratorConfig())
    return own, other_tool


async def test_diagnostics_cover_skills_from_every_root(two_roots: tuple[Path, Path]) -> None:
    own, other_tool = two_roots
    _write_skill(own, "my-notes")
    _write_skill(own, "my-todo")
    _write_skill(other_tool, "their-lint")

    diagnosis = await service.get_skill_diagnostics()

    assert diagnosis["total_skills"] == 3
    assert diagnosis["active_skills"] == 3
    assert diagnosis["findings"] == []
