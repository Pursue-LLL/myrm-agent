"""Catalog skills reach the agent runtime with every runtime-relevant field intact.

Skills bound to an agent flow Catalog ``Skill`` -> ``SkillMetadata`` -> availability gate -> trust
attenuation. A field dropped on that hop disables the feature it drives (gating, tool limits, always-on),
so the adapter's coverage of ``Skill`` is pinned field by field.
"""

from __future__ import annotations

from dataclasses import fields
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.backends.skills.types import (
    SecurityScanSummary,
    SkillMetadata,
    SkillPermission,
    SkillRequires,
    SkillTrust,
)
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.gates.requirements_availability import apply_requirements_availability_to_metadata
from app.core.skills.loader import _load_user_skill_backend  # noqa: PLC2701
from app.core.skills.models import Skill
from app.core.skills.runtime_metadata import skill_to_runtime_metadata

# Skill fields the runtime consumes; each must survive Skill -> SkillMetadata -> Skill.
CARRIED_FIELDS = frozenset(
    {
        "id",
        "description",
        "storage_path",
        "version",
        "token_cost",
        "requires",
        "trust",
        "always",
        "model_invocable",
        "user_invocable",
        "primary_env",
        "oauth_issuer",
        "required_oauth_issuers",
        "required_mcp_server_ids",
        "allowed_domains",
        "allowed_tools",
        "security",
        "evolution_locked",
        "scope_agent_id",
        "required_permissions",
        "config_schema",
    }
)
# ``name`` is carried in its runtime form (suffix-normalised); the rest is catalog display or lifecycle
# bookkeeping, and availability is always recomputed against the live environment instead of copied.
NORMALISED_FIELDS = frozenset({"name"})
CATALOG_ONLY_FIELDS = frozenset(
    {
        "type",
        "category",
        "icon_url",
        "tags",
        "available",
        "unavailable_reason",
        "author",
        "homepage",
        "user_trusted",
        "usage_stats",
        "origin_hash",
        "has_upstream_update",
        "installed_from",
        "last_replace_batch_id",
        "created_at",
        "updated_at",
    }
)


def _full_skill() -> Skill:
    return Skill(
        id="probe-id",
        type=SkillType.LOCAL,
        name="probe-skill",
        description="Probe description",
        storage_path="/skills/probe",
        version="2.3.1",
        token_cost=321,
        requires=SkillRequires(bins=["probe-bin"], env=["PROBE_KEY"], config=["probe.cfg"]),
        trust="installed",
        always=True,
        model_invocable=False,
        user_invocable=False,
        primary_env="PROBE_KEY",
        oauth_issuer="google",
        required_oauth_issuers=["google", "notion"],
        required_mcp_server_ids=["srv-a"],
        allowed_domains=["example.com"],
        allowed_tools=["file_read_tool", "bash_code_execute_tool"],
        security=SecurityScanSummary(score=90, trust_recommendation="installed", total_findings=0),
        evolution_locked=True,
        scope_agent_id="agent-1",
        required_permissions=["file_read", "file_write"],
        config_schema={"type": "object", "properties": {"mode": {"type": "string"}}},
    )


def _skill(**overrides: object) -> Skill:
    skill = Skill(id="s-id", type=SkillType.LOCAL, name="probe", description="d", storage_path="/p")
    for key, value in overrides.items():
        setattr(skill, key, value)
    return skill


def test_every_skill_field_is_classified() -> None:
    declared = {f.name for f in fields(Skill)}

    assert declared == CARRIED_FIELDS | NORMALISED_FIELDS | CATALOG_ONLY_FIELDS


def test_runtime_metadata_round_trips_every_carried_field() -> None:
    skill = _full_skill()

    meta = skill_to_runtime_metadata(skill)
    restored = Skill.from_metadata(meta, skill_id=skill.id, skill_type=skill.type)

    for name in sorted(CARRIED_FIELDS):
        assert getattr(restored, name) == getattr(skill, name), name
    assert meta.name == "probe_skill"
    assert meta.storage_skill_id == "probe-id"


def test_runtime_metadata_does_not_copy_availability() -> None:
    skill = _skill(available=False, unavailable_reason="stale snapshot")

    meta = skill_to_runtime_metadata(skill)

    assert (meta.available, meta.unavailable_reason) == (True, None)


def test_undeclared_requires_is_none_like_the_framework_parser() -> None:
    assert skill_to_runtime_metadata(_skill()).requires is None


@pytest.mark.parametrize(
    ("catalog_trust", "expected"),
    [
        ("trusted", SkillTrust.TRUSTED),
        ("installed", SkillTrust.INSTALLED),
        ("untrusted", SkillTrust.INSTALLED),
        ("unrecognised", SkillTrust.INSTALLED),
    ],
)
def test_trust_maps_to_the_framework_levels(catalog_trust: str, expected: SkillTrust) -> None:
    assert skill_to_runtime_metadata(_skill(trust=catalog_trust)).trust is expected


@pytest.mark.parametrize(
    ("trust", "security", "expected"),
    [
        ("installed", SecurityScanSummary(score=100, trust_recommendation="trusted", total_findings=0), True),
        ("installed", SecurityScanSummary(score=40, trust_recommendation="untrusted", total_findings=2), False),
        ("installed", None, False),
        ("trusted", None, True),
    ],
)
def test_scanner_clean_reflects_the_scan_summary(trust: str, security: SecurityScanSummary | None, expected: bool) -> None:
    assert skill_to_runtime_metadata(_skill(trust=trust, security=security)).scanner_clean is expected


def test_unknown_permissions_are_dropped() -> None:
    meta = skill_to_runtime_metadata(_skill(required_permissions=["file_read", "not_a_permission"]))

    assert meta.required_permissions == [SkillPermission.FILE_READ]


def test_invalid_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="name"):
        skill_to_runtime_metadata(_skill(name="   "))


@pytest.mark.asyncio
async def test_missing_bin_makes_a_bound_skill_unavailable_at_runtime() -> None:
    meta = skill_to_runtime_metadata(_skill(requires=SkillRequires(bins=["myrm-no-such-binary-xyz"])))

    with patch("app.core.skills.gates.requirements_availability._load_skill_env_vars", AsyncMock(return_value={})):
        await apply_requirements_availability_to_metadata([meta])

    assert meta.available is False
    assert "myrm-no-such-binary-xyz" in (meta.unavailable_reason or "")


@pytest.mark.asyncio
async def test_user_route_serves_runtime_complete_metadata() -> None:
    skill = _full_skill()
    skill.name = "my-local-skill"
    broken = _skill(name="   ")

    with patch("app.core.skills.store.service.skills_service.get_skills_by_ids", AsyncMock(return_value=[skill, broken])):
        backend = await _load_user_skill_backend(storage=AsyncMock(), skill_ids=[skill.id, broken.id], user_id="u")

    assert backend is not None
    listed: list[SkillMetadata] = await backend.list_skills()
    assert [m.name for m in listed] == ["my_local_skill"]
    meta = listed[0]
    assert meta.requires == skill.requires
    assert meta.trust is SkillTrust.INSTALLED
    assert meta.allowed_tools == skill.allowed_tools
    assert (meta.always, meta.model_invocable, meta.user_invocable) == (True, False, False)
    assert meta.primary_env == "PROBE_KEY"
