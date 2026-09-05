"""Unit tests for Agent filesystem bundle service (Agent-as-Code Dual-Track).

[INPUT]
- app.services.agent.agent_bundle_service::AgentBundleCodec, AgentBundleService
- app.services.agent.agent_service::AgentService

[OUTPUT]
- Unit tests validating encode/decode, filesystem workspace export/import, and traversal security

[POS]
Unit tests for the Agent filesystem bundle service layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.database.dto import AgentCreate
from app.services.agent.agent_bundle_service import (
    BUNDLE_DIR_NAME,
    MANIFEST_FILENAME,
    MCP_FILENAME,
    PROMPT_FILENAME,
    AgentBundleCodec,
    AgentBundleService,
)
from app.services.agent.agent_service import AgentService


def _create_mock_agent_profile(agent_id: str = "agent-alpha-1") -> AgentProfile:
    return AgentProfile(
        id=agent_id,
        display_name="Alpha Code Assistant",
        description="A specialized coding assistant.",
        system_prompt="You are a senior staff engineer with deep architecture skills.",
        model="claude-3-7-sonnet",
        skills=["skill-code-review", "skill-tdd"],
        metadata={
            "mcp_ids": ["mcp-github", "mcp-filesystem"],
            "mcp_tool_selections": {"mcp-github": ["list_prs", "get_diff"]},
            "agent_type": "individual",
            "personality_style": "professional",
            "prompt_mode": "full",
        },
    )


def test_encode_bundle_separates_prompt_and_manifest_and_mcp() -> None:
    agent_dict = {
        "id": "agent-alpha-1",
        "name": "Alpha Code Assistant",
        "description": "A specialized coding assistant.",
        "system_prompt": "You are a senior staff engineer with deep architecture skills.",
        "agent_type": "individual",
        "prompt_mode": "full",
        "personality_style": "professional",
        "mcp_ids": ["mcp-github", "mcp-filesystem"],
        "mcp_tool_selections": {"mcp-github": ["list_prs", "get_diff"]},
        "skill_ids": ["skill-code-review"],
    }

    files = AgentBundleCodec.encode_bundle(agent_dict)
    assert PROMPT_FILENAME in files
    assert MANIFEST_FILENAME in files
    assert MCP_FILENAME in files

    # AGENTS.md contains the system prompt
    assert files[PROMPT_FILENAME] == agent_dict["system_prompt"]

    # Manifest YAML contains metadata but not system_prompt
    assert "Alpha Code Assistant" in files[MANIFEST_FILENAME]
    assert "system_prompt" not in files[MANIFEST_FILENAME]

    # mcp.json contains structured tool config
    mcp_data = json.loads(files[MCP_FILENAME])
    assert mcp_data["mcp_ids"] == ["mcp-github", "mcp-filesystem"]
    assert "list_prs" in mcp_data["mcp_tool_selections"]["mcp-github"]


def test_encode_and_decode_bundle_roundtrip() -> None:
    agent_dict = {
        "name": "Roundtrip Agent",
        "description": "Roundtrip test description",
        "system_prompt": "Prompt for roundtrip testing.",
        "agent_type": "individual",
        "prompt_mode": "full",
        "personality_style": "professional",
        "mcp_ids": ["mcp-search"],
        "mcp_tool_selections": {"mcp-search": ["query"]},
        "skill_ids": ["skill-search"],
    }

    bundle = AgentBundleCodec.encode_bundle(agent_dict)
    decoded = AgentBundleCodec.decode_bundle(bundle)

    assert decoded["name"] == agent_dict["name"]
    assert decoded["description"] == agent_dict["description"]
    assert decoded["system_prompt"] == agent_dict["system_prompt"]
    assert decoded["mcp_ids"] == agent_dict["mcp_ids"]
    assert decoded["mcp_tool_selections"] == agent_dict["mcp_tool_selections"]


@pytest.mark.asyncio
async def test_export_agent_to_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _create_mock_agent_profile("test-agent-42")

    async def _mock_get_agent(agent_id: str) -> AgentProfile:
        assert agent_id == "test-agent-42"
        return profile

    monkeypatch.setattr(AgentService, "get_agent_by_id", _mock_get_agent)

    exported_dir = await AgentBundleService.export_agent_to_workspace("test-agent-42", tmp_path)
    expected_dir = tmp_path / BUNDLE_DIR_NAME / "test-agent-42"

    assert exported_dir == expected_dir
    assert (expected_dir / PROMPT_FILENAME).is_file()
    assert (expected_dir / MANIFEST_FILENAME).is_file()
    assert (expected_dir / MCP_FILENAME).is_file()
    assert (expected_dir / PROMPT_FILENAME).read_text(encoding="utf-8") == profile.system_prompt


@pytest.mark.asyncio
async def test_bundle_path_traversal_prevention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _create_mock_agent_profile("safe-agent")

    async def _mock_get_agent(agent_id: str) -> AgentProfile:
        return profile

    monkeypatch.setattr(AgentService, "get_agent_by_id", _mock_get_agent)

    with pytest.raises((ValueError, HTTPException)):
        await AgentBundleService.export_agent_to_workspace("../escape", tmp_path)


@pytest.mark.asyncio
async def test_import_agent_from_bundle_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_dir = tmp_path / "imported-agent"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    (bundle_dir / PROMPT_FILENAME).write_text("Imported prompt", encoding="utf-8")
    (bundle_dir / MANIFEST_FILENAME).write_text("name: Imported Agent\nschema_version: '1.0'\n", encoding="utf-8")
    (bundle_dir / MCP_FILENAME).write_text(json.dumps({"mcp_ids": ["mcp-1"]}), encoding="utf-8")

    created_dto: AgentCreate | None = None

    async def _mock_create_agent(create_dto: AgentCreate) -> SimpleNamespace:
        nonlocal created_dto
        created_dto = create_dto
        return SimpleNamespace(id="imported-agent-id")

    monkeypatch.setattr(AgentService, "create_agent", _mock_create_agent)

    imported_id = await AgentBundleService.import_agent_from_bundle_dir(bundle_dir)
    assert imported_id == "imported-agent-id"
    assert created_dto is not None
    assert created_dto.name == "Imported Agent"
    assert created_dto.system_prompt == "Imported prompt"
    assert created_dto.mcp_ids == ["mcp-1"]
