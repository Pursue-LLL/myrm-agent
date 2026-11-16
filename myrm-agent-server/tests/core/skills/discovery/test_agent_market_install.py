"""Chat agent market adapter: search unwraps market hits, installs delegate to market_install_flow."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, NonCallableMagicMock, create_autospec

import pytest
from myrm_agent_harness.agent.skills.market.service import EnrichedSearchResult
from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult, SkillSearchResult

from app.core.skills.discovery.agent_market_install import (
    AgentSessionSkillMarketBackend,
    install_from_url_for_agent_session,
)
from app.core.skills.discovery.market_install_flow import MarketInstallFlowResult
from app.core.skills.marketplace.market_service import SkillMarketService


@dataclass(frozen=True)
class _MountStub:
    mounted: bool
    agent_id: str = "agent-1"
    mount_skill_id: str = "prebuilt::demo"


def _flow_result() -> MarketInstallFlowResult:
    return MarketInstallFlowResult(
        result=SkillInstallResult(success=True, skill_id="prebuilt::demo", skill_name="Demo"),
        mount_result=_MountStub(mounted=True),
    )


def _market() -> NonCallableMagicMock:
    """Autospec of the real facade, so a call the facade does not accept fails here instead of in production."""
    return create_autospec(SkillMarketService, instance=True)


def _hit() -> SkillSearchResult:
    return SkillSearchResult(
        id="demo",
        name="Demo",
        description="A demo skill",
        source="clawhub",
        author="author",
        install_url="https://example.com/demo",
        install_method="git",
    )


@pytest.mark.asyncio
async def test_install_delegates_to_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    flow_fn = AsyncMock(return_value=_flow_result())
    adopt = AsyncMock()
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.run_market_install_flow_by_id",
        flow_fn,
    )
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.complete_discovery_adoption",
        adopt,
    )
    backend = AgentSessionSkillMarketBackend(_market())

    out = await backend.install("skill-a", "clawhub", user_id="u1")

    assert out.skill_id == "prebuilt::demo"
    flow_fn.assert_awaited_once_with(
        "skill-a",
        "clawhub",
        agent_id=None,
        mount_to_agent=True,
    )
    adopt.assert_awaited_once_with("agent-1", "prebuilt::demo")


@pytest.mark.asyncio
async def test_install_from_url_delegates_to_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    flow_fn = AsyncMock(return_value=_flow_result())
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.run_market_install_flow_from_url",
        flow_fn,
    )

    await install_from_url_for_agent_session("https://github.com/o/r", None)

    flow_fn.assert_awaited_once_with(
        "https://github.com/o/r",
        agent_id=None,
        mount_to_agent=True,
    )


@pytest.mark.asyncio
async def test_search_unwraps_market_hits_and_forwards_arguments() -> None:
    market = _market()
    hit = _hit()
    market.search.return_value = [EnrichedSearchResult(result=hit, installed_version="1.0.0", upgrade_available=True)]

    assert await AgentSessionSkillMarketBackend(market).search("q", limit=3) == [hit]
    market.search.assert_awaited_once_with("q", limit=3)


@pytest.mark.asyncio
async def test_search_forwards_the_protocol_default_limit() -> None:
    market = _market()
    market.search.return_value = []

    assert await AgentSessionSkillMarketBackend(market).search("q") == []
    market.search.assert_awaited_once_with("q", limit=10)
