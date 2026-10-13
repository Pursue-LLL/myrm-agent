"""One definition of the skills root: where the agent writes skills is the first root the catalog scans."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path

from app.core.skills import effective_skill_ids
from app.core.skills.creation.service import SkillCreationService
from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS, LOCAL_SKILLS_DIR, _as_home_relative


def test_catalog_primary_root_is_the_directory_the_creation_service_writes_to() -> None:
    assert Path(DEFAULT_LOCAL_SKILL_PATHS[0]).expanduser() == LOCAL_SKILLS_DIR
    assert SkillCreationService().base_path == LOCAL_SKILLS_DIR


def test_a_root_under_home_is_shown_the_way_users_configure_it() -> None:
    assert _as_home_relative(Path.home() / ".myrm" / "skills") == "~/.myrm/skills"


def test_a_root_outside_home_stays_absolute() -> None:
    assert _as_home_relative(Path("/srv/myrm-data/skills")) == "/srv/myrm-data/skills"


def test_legacy_local_id_resolves_against_the_writer_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "release-notes").mkdir()
    monkeypatch.setattr(effective_skill_ids, "LOCAL_SKILLS_DIR", tmp_path)

    resolved = effective_skill_ids.normalize_local_skill_id("local::release-notes")

    assert resolved == local_skill_id_from_path(tmp_path / "release-notes")
