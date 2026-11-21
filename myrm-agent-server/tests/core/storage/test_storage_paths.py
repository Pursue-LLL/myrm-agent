"""Tests for storage path utilities.

Covers path generation functions.
"""

from __future__ import annotations

from app.core.storage.paths import (
    FILE_METADATA_SUFFIX,
    SKILLS_ROOT_PREFIX,
    get_file_metadata_path,
    get_file_reference_path,
    get_file_storage_path,
    get_skill_file_path,
    get_skill_metadata_path,
    get_skill_storage_path,
    get_skills_type_prefix,
    get_user_config_path,
    get_user_files_prefix,
    get_user_skill_config_path,
)
from app.core.storage.types import FilePurpose, SkillType


class TestFilePathGeneration:
    def test_get_file_storage_path_upload(self) -> None:
        path = get_file_storage_path("file_abc", FilePurpose.UPLOAD)
        assert path == "files/uploads/file_abc"

    def test_get_file_storage_path_generated(self) -> None:
        path = get_file_storage_path("file_xyz", FilePurpose.GENERATED)
        assert path == "files/generated/file_xyz"

    def test_get_file_storage_path_skill(self) -> None:
        path = get_file_storage_path("file_xyz", FilePurpose.SKILL)
        assert path == "files/skill/file_xyz"

    def test_get_file_metadata_path(self) -> None:
        path = get_file_metadata_path("files/uploads/file_abc")
        assert path == f"files/uploads/file_abc{FILE_METADATA_SUFFIX}"

    def test_get_user_files_prefix_all(self) -> None:
        prefix = get_user_files_prefix()
        assert prefix == "files/"

    def test_get_user_files_prefix_with_purpose(self) -> None:
        prefix = get_user_files_prefix(FilePurpose.GENERATED)
        assert prefix == "files/generated/"


class TestFileReferencePath:
    def test_key_keeps_every_directory_of_the_real_path(self) -> None:
        assert get_file_reference_path("chat1", "/home/me/ws/proj/index.html") == "sandboxes/chat1/home/me/ws/proj/index.html"

    def test_directories_named_workspace_are_not_folded_away(self) -> None:
        inside = get_file_reference_path("chat1", "/tmp/x/workspace/proj/index.html")
        outside = get_file_reference_path("chat1", "/tmp/x/proj/index.html")
        team = get_file_reference_path("chat1", "/tmp/x/team-workspace/proj/index.html")
        folded = get_file_reference_path("chat1", "/tmp/x/team-proj/index.html")

        assert len({inside, outside, team, folded}) == 4

    def test_a_colon_in_a_file_name_keeps_the_file_distinct(self) -> None:
        assert get_file_reference_path("chat1", "/tmp/a:b.html") != get_file_reference_path("chat1", "/tmp/ab.html")

    def test_windows_drive_colon_is_removed_from_the_key(self) -> None:
        assert get_file_reference_path("chat1", "C:/Users/me/ws/index.html") == "sandboxes/chat1/C/Users/me/ws/index.html"

    def test_key_is_per_chat(self) -> None:
        assert get_file_reference_path("chat1", "/tmp/a.html") != get_file_reference_path("chat2", "/tmp/a.html")


class TestSkillPathGeneration:
    def test_get_skill_storage_path_prebuilt(self) -> None:
        path = get_skill_storage_path(SkillType.PREBUILT, "pdf-generator")
        assert path == "skills/prebuilt/pdf-generator"

    def test_get_skill_storage_path_local(self) -> None:
        path = get_skill_storage_path(SkillType.LOCAL, "my-custom-skill")
        assert path == "skills/local/my-custom-skill"

    def test_get_skills_type_prefix(self) -> None:
        prefix = get_skills_type_prefix(SkillType.PREBUILT)
        assert prefix == f"{SKILLS_ROOT_PREFIX}/prebuilt/"

    def test_get_skill_file_path(self) -> None:
        path = get_skill_file_path(SkillType.PREBUILT, "pdf-generator", "SKILL.md")
        assert path == "skills/prebuilt/pdf-generator/SKILL.md"

    def test_get_skill_metadata_path(self) -> None:
        path = get_skill_metadata_path(SkillType.PREBUILT, "pdf-generator")
        assert path == "skills/prebuilt/pdf-generator/_metadata.json"


class TestUserConfigPaths:
    def test_get_user_config_path(self) -> None:
        path = get_user_config_path("skills")
        assert path == "config/skills.json"

    def test_get_user_skill_config_path(self) -> None:
        path = get_user_skill_config_path()
        assert path == "config/skills.json"
