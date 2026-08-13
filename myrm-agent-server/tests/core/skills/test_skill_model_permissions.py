"""Tests for required_permissions on the business-layer Skill model.

Covers from_metadata mapping (framework enum -> plain strings) and
to_dict/from_dict round-trip persistence of the field.
"""

from __future__ import annotations

from myrm_agent_harness.backends.skills.types import (
    SkillMetadata,
    SkillPermission,
    SkillTrust,
)

from app.core.skills.models import Skill, SkillType


def _make_metadata(
    permissions: list[SkillPermission] | None = None,
) -> SkillMetadata:
    return SkillMetadata(
        name="perm-skill",
        description="desc",
        storage_path="/tmp/perm-skill",
        trust=SkillTrust.INSTALLED,
        required_permissions=list(permissions or []),
    )


class TestSkillRequiredPermissionsFromMetadata:
    def test_from_metadata_maps_enum_values_to_strings(self) -> None:
        meta = _make_metadata(
            [SkillPermission.FILE_WRITE, SkillPermission.SHELL_EXEC]
        )
        skill = Skill.from_metadata(
            meta,
            skill_id="local::abc",
            skill_type=SkillType.LOCAL,
        )
        assert skill.required_permissions == ["file_write", "shell_exec"]

    def test_from_metadata_empty_list(self) -> None:
        skill = Skill.from_metadata(
            _make_metadata([]),
            skill_id="local::abc",
            skill_type=SkillType.LOCAL,
        )
        assert skill.required_permissions == []

    def test_from_metadata_absent_defaults_to_empty(self) -> None:
        meta = _make_metadata()
        del meta.required_permissions
        skill = Skill.from_metadata(
            meta,
            skill_id="local::abc",
            skill_type=SkillType.LOCAL,
        )
        assert skill.required_permissions == []


class TestSkillRequiredPermissionsSerialization:
    def _make_skill(self) -> Skill:
        return Skill(
            id="local::abc",
            type=SkillType.LOCAL,
            name="perm-skill",
            description="desc",
            storage_path="/tmp/perm-skill",
            required_permissions=["file_write", "shell_exec"],
        )

    def test_to_dict_includes_required_permissions(self) -> None:
        assert self._make_skill().to_dict()["required_permissions"] == [
            "file_write",
            "shell_exec",
        ]

    def test_from_dict_round_trip(self) -> None:
        d = self._make_skill().to_dict()
        restored = Skill.from_dict(d)
        assert restored.required_permissions == ["file_write", "shell_exec"]

    def test_from_dict_missing_field_defaults_to_empty(self) -> None:
        d = self._make_skill().to_dict()
        del d["required_permissions"]
        restored = Skill.from_dict(d)
        assert restored.required_permissions == []
