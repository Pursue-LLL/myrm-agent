"""Tests for the local skill backend and the workspace skill scan on folders that are not tidy.

[INPUT]
- backends.skills.local::LocalSkillBackend, scan_workspace_skills (POS: the directory-backed skill source under test)
- backends.skills.snapshot::SQLiteSkillSnapshot (POS: the fast path both readers prefer when a snapshot file exists)
- real files in a temp directory (POS: the file system decides what is a skill, nothing is faked)

[OUTPUT]
- Fails when a skill folder that is malformed, oversized, archived, not UTF-8, a directory in place of ``SKILL.md`` or unreadable stops the
  others from loading, when an archived skill is listed, or when a resource or content lookup answers differently from the files.

[POS]
The happy path and the config schema have their own files; this one pins that every way a skill folder can be wrong costs only that skill.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.backends.skills import local as local_module
from myrm_agent_harness.backends.skills._runtime import build_skill_metadata as real_build
from myrm_agent_harness.backends.skills._utils import _MAX_SKILL_FILE_SIZE, SkillFrontmatter
from myrm_agent_harness.backends.skills._utils import parse_skill_frontmatter as real_parse
from myrm_agent_harness.backends.skills.local import LocalSkillBackend, scan_workspace_skills
from myrm_agent_harness.backends.skills.snapshot import SQLiteSkillSnapshot
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus, SkillMetadata, SkillTrust

_BODY = "---\nname: {name}\ndescription: A skill used by the local backend tests.\n---\n\nBody.\n"


def _skill(root: Path, name: str, *, stats: str | dict[str, str] | None = None) -> Path:
    """A valid skill folder; ``stats`` becomes its ``.stats.json`` (a string is written as is)."""
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(_BODY.format(name=name), encoding="utf-8")
    if stats is not None:
        (directory / ".stats.json").write_text(stats if isinstance(stats, str) else json.dumps(stats), encoding="utf-8")
    return directory


def _names(skills: list[SkillMetadata]) -> list[str]:
    return sorted(skill.name for skill in skills)


def _snapshot_of(root: Path, *skill_dirs: Path) -> None:
    snapshot = SQLiteSkillSnapshot(root / ".skills_snapshot.sqlite")
    for directory in skill_dirs:
        assert snapshot.upsert_from_path(directory / "SKILL.md", workspace_root=root)


class TestConstruction:
    def test_a_missing_directory_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Skills directory not found"):
            LocalSkillBackend(tmp_path / "absent")

    def test_a_file_in_place_of_the_directory_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "skills").write_text("not a directory")

        with pytest.raises(ValueError, match="not a directory"):
            LocalSkillBackend(tmp_path / "skills")


class TestListSkills:
    @pytest.mark.asyncio
    async def test_every_way_a_folder_can_be_wrong_costs_only_that_skill(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _skill(tmp_path, "good")
        (tmp_path / "notes.txt").write_text("a file, not a skill folder")
        (tmp_path / "empty").mkdir()
        _skill(tmp_path, "huge")
        # A valid skill padded past the limit: only the size check can keep it out.
        (tmp_path / "huge" / "SKILL.md").write_text(
            _BODY.format(name="huge") + "x" * _MAX_SKILL_FILE_SIZE, encoding="utf-8"
        )
        (tmp_path / "nofrontmatter").mkdir()
        (tmp_path / "nofrontmatter" / "SKILL.md").write_text("no frontmatter here\n")
        (tmp_path / "latin").mkdir()
        (tmp_path / "latin" / "SKILL.md").write_bytes(b"---\nname: latin\ndescription: \xff\xfe\n---\n")

        with caplog.at_level(logging.DEBUG, logger=local_module.logger.name):
            skills = await LocalSkillBackend(tmp_path, use_snapshot=False).list_skills()

        assert _names(skills) == ["good"]
        assert "Skipping 'empty': no SKILL.md found" in caplog.text
        assert "Skipping 'huge'" in caplog.text
        assert "Invalid skill 'nofrontmatter'" in caplog.text
        assert "Cannot read 'latin/SKILL.md'" in caplog.text

    @pytest.mark.asyncio
    async def test_an_unexpected_error_skips_only_that_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _skill(tmp_path, "good")
        _skill(tmp_path, "boom")

        def build(
            skill_name: str,
            frontmatter: SkillFrontmatter,
            storage_path: str,
            content: str,
            trust: SkillTrust,
            workspace_root: Path | None = None,
        ) -> SkillMetadata:
            if skill_name == "boom":
                raise RuntimeError("the builder broke")
            return real_build(skill_name, frontmatter, storage_path, content, trust, workspace_root)

        monkeypatch.setattr(f"{local_module.__name__}.build_skill_metadata", build)

        with caplog.at_level(logging.ERROR, logger=local_module.logger.name):
            skills = await LocalSkillBackend(tmp_path, use_snapshot=False).list_skills()

        assert _names(skills) == ["good"]
        assert "Unexpected error loading skill 'boom'" in caplog.text

    @pytest.mark.asyncio
    async def test_lifecycle_stats_apply_and_an_archived_skill_is_hidden(self, tmp_path: Path) -> None:
        _skill(tmp_path, "plain")
        _skill(tmp_path, "worn", stats={"lifecycle_status": "stale"})
        _skill(tmp_path, "retired", stats={"lifecycle_status": "archived"})
        _skill(tmp_path, "garbled", stats="{not json")

        skills = await LocalSkillBackend(tmp_path, use_snapshot=False).list_skills()

        by_name = {skill.name: skill for skill in skills}
        assert sorted(by_name) == ["garbled", "plain", "worn"]
        assert by_name["worn"].usage_stats.lifecycle_status == SkillLifecycleStatus.STALE
        assert by_name["garbled"].usage_stats.lifecycle_status == SkillLifecycleStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_the_snapshot_path_applies_stats_and_hides_an_archived_skill_too(self, tmp_path: Path) -> None:
        worn = _skill(tmp_path, "worn", stats={"lifecycle_status": "stale"})
        retired = _skill(tmp_path, "retired", stats={"lifecycle_status": "archived"})
        plain = _skill(tmp_path, "plain")
        _snapshot_of(tmp_path, worn, retired, plain)

        skills = await LocalSkillBackend(tmp_path).list_skills()

        by_name = {skill.name: skill for skill in skills}
        assert sorted(by_name) == ["plain", "worn"]
        assert by_name["worn"].usage_stats.lifecycle_status == SkillLifecycleStatus.STALE

    @pytest.mark.asyncio
    async def test_load_skills_returns_only_the_asked_for_names(self, tmp_path: Path) -> None:
        for name in ("one", "two", "three"):
            _skill(tmp_path, name)

        skills = await LocalSkillBackend(tmp_path, use_snapshot=False).load_skills(["one", "three", "absent"])

        assert _names(skills) == ["one", "three"]


class TestContentAndResources:
    @pytest.mark.asyncio
    async def test_content_and_resources_answer_from_the_files(self, tmp_path: Path) -> None:
        demo = _skill(tmp_path, "demo")
        (demo / "refs").mkdir()
        (demo / "refs" / "a.md").write_text("A")
        (demo / "script.py").write_text("print()")
        backend = LocalSkillBackend(tmp_path, use_snapshot=False)

        assert await backend.get_skill_content("demo") == (demo / "SKILL.md").read_text(encoding="utf-8")
        assert await backend.get_skill_resources("demo", "refs/a.md") == b"A"
        assert sorted(await backend.list_skill_resources("demo")) == sorted([str(Path("refs") / "a.md"), "script.py"])

    @pytest.mark.asyncio
    async def test_what_is_not_there_is_reported_not_invented(self, tmp_path: Path) -> None:
        demo = _skill(tmp_path, "demo")
        (demo / "refs").mkdir()
        backend = LocalSkillBackend(tmp_path, use_snapshot=False)

        with pytest.raises(FileNotFoundError, match=r"SKILL\.md not found"):
            await backend.get_skill_content("absent")
        with pytest.raises(FileNotFoundError, match="Resource not found"):
            await backend.get_skill_resources("demo", "missing.md")
        with pytest.raises(FileNotFoundError, match="Resource not found"):
            await backend.get_skill_resources("demo", "refs")
        assert await backend.list_skill_resources("absent") == []


class TestWorkspaceScan:
    def test_a_root_that_is_not_a_directory_has_no_skills(self, tmp_path: Path) -> None:
        assert scan_workspace_skills(tmp_path / "absent", disclosure_only=True) == []

    def test_the_walk_stops_at_the_depth_limit(self, tmp_path: Path) -> None:
        _skill(tmp_path / "a" / "b", "deep")

        assert _names(scan_workspace_skills(tmp_path, max_depth=2, use_snapshot=False, disclosure_only=True)) == [
            "deep"
        ]
        assert scan_workspace_skills(tmp_path, max_depth=1, use_snapshot=False, disclosure_only=True) == []

    def test_a_folder_that_cannot_be_listed_costs_only_itself(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _skill(tmp_path / "open", "found")
        (tmp_path / "locked").mkdir()
        real_iterdir = Path.iterdir

        def refuse_the_locked_folder(self: Path) -> Iterator[Path]:
            if self.name == "locked":
                raise PermissionError("not allowed")
            return real_iterdir(self)

        monkeypatch.setattr(Path, "iterdir", refuse_the_locked_folder)

        skills = scan_workspace_skills(tmp_path, use_snapshot=False, disclosure_only=True)

        assert _names(skills) == ["found"]

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows refuses to open a directory, so the skip is a warning there"
    )
    def test_a_directory_in_place_of_skill_md_is_skipped_without_a_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "odd" / "SKILL.md").mkdir(parents=True)
        _skill(tmp_path, "fine")

        with caplog.at_level(logging.DEBUG, logger=local_module.logger.name):
            skills = scan_workspace_skills(tmp_path, use_snapshot=False, disclosure_only=True)

        assert _names(skills) == ["fine"]
        assert "'odd': SKILL.md is not a regular file" in caplog.text
        assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []

    def test_an_unexpected_error_skips_only_that_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _skill(tmp_path, "good")
        _skill(tmp_path, "boom")

        def parse(content: str, skill_dir_name: str) -> SkillFrontmatter:
            if skill_dir_name == "boom":
                raise RuntimeError("the parser broke")
            return real_parse(content, skill_dir_name)

        monkeypatch.setattr(f"{local_module.__name__}.parse_skill_frontmatter", parse)

        with caplog.at_level(logging.WARNING, logger=local_module.logger.name):
            skills = scan_workspace_skills(tmp_path, use_snapshot=False, disclosure_only=True)

        assert _names(skills) == ["good"]
        assert "Unexpected error loading workspace skill 'boom'" in caplog.text

    def test_the_snapshot_path_applies_stats_and_hides_an_archived_skill(self, tmp_path: Path) -> None:
        worn = _skill(tmp_path, "worn", stats={"lifecycle_status": "stale"})
        retired = _skill(tmp_path, "retired", stats={"lifecycle_status": "archived"})
        _snapshot_of(tmp_path, worn, retired)

        skills = scan_workspace_skills(tmp_path, use_snapshot=True, disclosure_only=True)

        assert _names(skills) == ["worn"]
        assert skills[0].usage_stats.lifecycle_status == SkillLifecycleStatus.STALE
