"""Readiness reads installation state truthfully: imported-but-disabled connectors, installed skills.

An imported expert references connectors (installed disabled by default) and skills
(installed into the catalog). The report must tell "installed but not enabled" apart
from "does not exist", and must recognise skills that live in the catalog.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
from app.services.agent.readiness import AgentReadinessItem, AgentReadinessReport, ReadinessCode, ReadinessLevel
from app.services.agent.readiness.resolver import _check_mcp, _check_skills, resolve_agent_readiness


def _profile(*, mcp_ids: tuple[str, ...] = (), skill_ids: tuple[str, ...] = ()) -> ResolvedAgentProfile:
    return ResolvedAgentProfile(
        agent_id="agent-1",
        skill_ids=skill_ids,
        mcp_ids=mcp_ids,
        enabled_builtin_tools=("web_fetch",),
    )


def _server(name: str, *, enabled: bool) -> dict[str, object]:
    return {"name": name, "type": "sse", "url": "https://example.com/mcp", "enabled": enabled}


@pytest.mark.asyncio
async def test_disabled_connector_is_reported_as_installed_but_not_enabled() -> None:
    items = await _check_mcp(_profile(mcp_ids=("imported",)), {"mcpConfigs": [_server("imported", enabled=False)]})

    assert len(items) == 1
    assert items[0].reason == "1 MCP server(s) installed but not enabled"
    assert "imported" in (items[0].next_action or "")
    assert items[0].settings_path == "/settings/mcp"
    assert (items[0].code, items[0].names, items[0].count) == (ReadinessCode.MCP_NOT_ENABLED, ("imported",), 1)


@pytest.mark.asyncio
async def test_unknown_connector_is_reported_as_not_found_separately_from_disabled_ones() -> None:
    mcp_dict: dict[str, object] = {"mcpConfigs": [_server("imported", enabled=False), _server("active", enabled=True)]}

    items = await _check_mcp(_profile(mcp_ids=("imported", "active", "ghost")), mcp_dict)

    assert [item.reason for item in items] == [
        "1 MCP server(s) installed but not enabled",
        "1 MCP server(s) not found in config",
    ]
    assert "ghost" in (items[1].next_action or "")
    assert [(item.code, item.names) for item in items] == [
        (ReadinessCode.MCP_NOT_ENABLED, ("imported",)),
        (ReadinessCode.MCP_NOT_FOUND, ("ghost",)),
    ]


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Installed catalog (what ``skills_service`` lists) and evolution store (managed records)."""
    state = SimpleNamespace(installed_ids=[], managed_ids=set())
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service",
        SimpleNamespace(list_skills=AsyncMock(side_effect=lambda: [SimpleNamespace(id=i) for i in state.installed_ids])),
    )
    monkeypatch.setattr(
        "app.services.skills.evolution_review.disk.get_skill_store",
        lambda: SimpleNamespace(get_skill=lambda sid: object() if sid in state.managed_ids else None),
    )
    return state


@pytest.mark.asyncio
async def test_skills_installed_in_the_catalog_are_found(catalog: SimpleNamespace) -> None:
    catalog.installed_ids = ["local::abc123", "web-research"]

    items = await _check_skills(_profile(skill_ids=("local::abc123", "web-research")))

    assert items == []


@pytest.mark.asyncio
async def test_evolution_managed_skills_are_found(catalog: SimpleNamespace) -> None:
    catalog.managed_ids = {"managed-1"}

    assert await _check_skills(_profile(skill_ids=("managed-1",))) == []


@pytest.mark.asyncio
async def test_missing_skills_are_listed(catalog: SimpleNamespace) -> None:
    catalog.installed_ids = ["local::abc123"]

    items = await _check_skills(_profile(skill_ids=("local::abc123", "local::gone")))

    assert len(items) == 1
    assert items[0].dimension == "skills"
    assert items[0].reason == "1 skill(s) not found: local::gone"
    # Skill ids are internal, so clients get a count, never the ids.
    assert (items[0].code, items[0].names, items[0].count) == (ReadinessCode.SKILLS_MISSING, (), 1)


@pytest.mark.asyncio
async def test_expert_without_skills_has_nothing_to_check() -> None:
    assert await _check_skills(_profile()) == []


@pytest.mark.asyncio
async def test_an_unknown_agent_is_blocked_under_its_own_dimension() -> None:
    resolver = SimpleNamespace(resolve=AsyncMock(return_value=None))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("app.services.agent.readiness.resolver.get_agent_profile_resolver", lambda: resolver)
        report = await resolve_agent_readiness("ghost-agent")

    assert report.overall_level is ReadinessLevel.BLOCKED
    assert [(item.dimension, item.code) for item in report.items] == [("agent", ReadinessCode.AGENT_NOT_FOUND)]


def test_the_wire_shape_carries_the_code_names_and_count_next_to_the_english_diagnostics() -> None:
    report = AgentReadinessReport(
        overall_level=ReadinessLevel.WARNING,
        agent_id="agent-1",
        items=(
            AgentReadinessItem(
                dimension="mcp",
                level=ReadinessLevel.WARNING,
                code=ReadinessCode.MCP_MISSING_SECRETS,
                reason="MCP servers missing secrets: SLACK_TOKEN",
                next_action="Add the missing secrets in agent settings",
                settings_path="/settings/agents",
                names=("SLACK_TOKEN",),
                count=1,
            ),
        ),
    )

    items = report.to_dict()["items"]
    assert isinstance(items, list)
    item = items[0]

    assert item["code"] == "mcp_missing_secrets"
    assert item["names"] == ["SLACK_TOKEN"]
    assert item["count"] == 1
    assert item["reason"] == "MCP servers missing secrets: SLACK_TOKEN"
