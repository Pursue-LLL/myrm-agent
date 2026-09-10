"""Architecture guard: Skill required connectors (OAuth issuers & MCP servers) preflight & minimal mount.

[INPUT]
- SKILL.md frontmatter with required_oauth_issuers & required_mcp_server_ids
- myrm_agent_harness.backends.skills.types.SkillMetadata
- app.core.skills.models.Skill
- app.core.skills.gates.oauth_availability

[OUTPUT]
- Tests verifying:
  1. Frontmatter parser extracts multi-connector declarations (required_oauth_issuers, required_mcp_server_ids).
  2. Skill model preserves and serializes required_oauth_issuers and required_mcp_server_ids.
  3. Dynamic preflight gate marks skills unavailable when declared required_oauth_issuers are disconnected.
  4. Dynamic preflight gate marks skills available when all declared required_oauth_issuers are connected.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.backends.skills._utils import parse_skill_frontmatter
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillTrust
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.gates.oauth_availability import (
    apply_integration_oauth_availability,
    apply_integration_oauth_to_metadata,
)
from app.core.skills.models import Skill


def test_frontmatter_parses_multi_connector_dependencies() -> None:
    sample_frontmatter = """---
name: enterprise-meeting-minutes
description: Automated meeting minutes synthesis with external calendar & docs integration.
required_oauth_issuers:
  - tencent_meeting
  - google_workspace
required_mcp_server_ids:
  - mcp-tencent-docs
  - mcp-calendar
---
# Meeting Minutes
"""
    fm = parse_skill_frontmatter(sample_frontmatter, "enterprise-meeting-minutes")
    assert fm.required_oauth_issuers == ["tencent_meeting", "google_workspace"]
    assert fm.required_mcp_server_ids == ["mcp-tencent-docs", "mcp-calendar"]


def test_skill_model_serializes_and_deserializes_required_connectors() -> None:
    meta = SkillMetadata(
        name="custom-collab-skill",
        description="Collaboration skill with multi-connectors",
        storage_skill_id="custom-collab-skill",
        required_oauth_issuers=["slack_oauth", "github_oauth"],
        required_mcp_server_ids=["mcp-github"],
        trust=SkillTrust.TRUSTED,
    )

    skill = Skill.from_metadata(
        meta,
        skill_id="custom-collab-skill",
        skill_type=SkillType.PREBUILT,
    )
    assert skill.required_oauth_issuers == ["slack_oauth", "github_oauth"]
    assert skill.required_mcp_server_ids == ["mcp-github"]

    serialized = skill.to_dict()
    assert serialized["required_oauth_issuers"] == ["slack_oauth", "github_oauth"]
    assert serialized["required_mcp_server_ids"] == ["mcp-github"]

    restored = Skill.from_dict(serialized)
    assert restored.required_oauth_issuers == ["slack_oauth", "github_oauth"]
    assert restored.required_mcp_server_ids == ["mcp-github"]


@pytest.mark.asyncio
async def test_dynamic_preflight_gate_marks_skill_unavailable_when_issuer_missing() -> None:
    skill = Skill(
        id="custom-oauth-gated-skill",
        type=SkillType.PREBUILT,
        name="Custom Gated Skill",
        description="Skill needing Notion OAuth",
        storage_path="skills/custom-oauth-gated-skill",
        required_oauth_issuers=["notion_oauth"],
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.gates.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=False),
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is False
    assert "Connect notion_oauth in Settings" in (skill.unavailable_reason or "")


@pytest.mark.asyncio
async def test_dynamic_preflight_gate_marks_skill_available_when_issuers_connected() -> None:
    skill = Skill(
        id="custom-oauth-gated-skill",
        type=SkillType.PREBUILT,
        name="Custom Gated Skill",
        description="Skill needing Zoom OAuth",
        storage_path="skills/custom-oauth-gated-skill",
        required_oauth_issuers=["zoom_oauth"],
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.gates.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=True),
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is True
    assert skill.unavailable_reason is None


@pytest.mark.asyncio
async def test_metadata_dynamic_preflight_gate_enforcement() -> None:
    meta = SkillMetadata(
        name="metadata-gated-skill",
        description="Runtime metadata needing Figma",
        storage_skill_id="metadata-gated-skill",
        required_oauth_issuers=["figma_oauth"],
        trust=SkillTrust.TRUSTED,
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.gates.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=False),
    ):
        await apply_integration_oauth_to_metadata([meta], db)

    assert meta.available is False
    assert "Connect figma_oauth in Settings" in (meta.unavailable_reason or "")
