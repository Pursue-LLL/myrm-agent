"""Tests for Skill.to_dict / from_dict persistence and the prebuilt metadata reader.

Pins the contract that persisted skill metadata never gates visibility: a legacy
``is_active`` key is ignored on read and never written back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills.models import Skill, SkillType
from app.core.skills.store import reader
from app.core.storage.paths import get_skill_metadata_path


def _minimal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "demo-skill",
        "type": "prebuilt",
        "name": "demo-skill",
        "description": "demo",
        "storage_path": "skills/prebuilt/demo-skill",
    }
    payload.update(overrides)
    return payload


class TestLegacyIsActiveKey:
    def test_from_dict_ignores_legacy_key(self) -> None:
        skill = Skill.from_dict(_minimal_payload(is_active=False))
        assert skill.id == "demo-skill"
        assert not hasattr(skill, "is_active")

    def test_to_dict_does_not_write_the_key(self) -> None:
        assert "is_active" not in Skill.from_dict(_minimal_payload(is_active=False)).to_dict()

    @pytest.mark.asyncio
    async def test_prebuilt_listing_keeps_skills_with_legacy_inactive_metadata(self, tmp_path: Path) -> None:
        storage = LocalStorageBackend(str(tmp_path))
        metadata_path = get_skill_metadata_path(SkillType.PREBUILT, "demo-skill")
        await storage.write_text(metadata_path, json.dumps(_minimal_payload(is_active=False)))

        skills = await reader.list_prebuilt_skills(storage)

        assert [s.id for s in skills] == ["demo-skill"]


class TestSkillRoundTrip:
    def test_oauth_and_mcp_requirements_survive_round_trip(self) -> None:
        skill = Skill.from_dict(
            _minimal_payload(
                oauth_issuer="github",
                required_oauth_issuers=["github", "linear"],
                required_mcp_server_ids=["notion"],
            )
        )
        restored = Skill.from_dict(skill.to_dict())
        assert restored.oauth_issuer == "github"
        assert restored.required_oauth_issuers == ["github", "linear"]
        assert restored.required_mcp_server_ids == ["notion"]

    def test_dict_valued_fields_are_copied_and_non_dicts_become_none(self) -> None:
        schema = {"type": "object"}
        skill = Skill.from_dict(_minimal_payload(config_schema=schema, usage_stats="oops", installed_from=["x"]))
        assert skill.config_schema == schema
        assert skill.config_schema is not schema
        assert skill.usage_stats is None
        assert skill.installed_from is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("12", 12), (12, 12), (12.7, 12), (None, None), ([], None), ({}, None)],
    )
    def test_token_cost_coercion(self, raw: object, expected: int | None) -> None:
        assert Skill.from_dict(_minimal_payload(token_cost=raw)).token_cost == expected
