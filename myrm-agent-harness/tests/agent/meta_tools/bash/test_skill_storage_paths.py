"""The bash tool stages skills from host directories, so storage keys must resolve against the storage root."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.bash._tool.helpers import resolve_skill_storage_paths
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.storage import storage_config


def _skill(name: str, storage_path: str | None) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=f"{name} skill",
        storage_path=storage_path,
        model_invocable=True,
        available=True,
    )


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(storage_config, "base_path", str(tmp_path))
    return tmp_path


def test_a_storage_key_resolves_against_the_storage_root_not_the_working_directory(
    storage_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    monkeypatch.chdir(elsewhere)

    paths = resolve_skill_storage_paths([_skill("demo", "skills/prebuilt/demo")])

    assert paths == [str(storage_root / "skills" / "prebuilt" / "demo")]


def test_a_local_skill_directory_is_kept_as_is(storage_root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    local_dir = tmp_path_factory.mktemp("local") / "my-skill"

    assert resolve_skill_storage_paths([_skill("my-skill", str(local_dir))]) == [str(local_dir)]


def test_a_skill_without_a_storage_path_is_left_out(storage_root: Path) -> None:
    skills = [_skill("virtual", None), _skill("demo", "skills/prebuilt/demo")]

    assert resolve_skill_storage_paths(skills) == [str(storage_root / "skills" / "prebuilt" / "demo")]
