"""Chat agent market adapter: search unwraps market hits, installs delegate to market_install_flow."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, NonCallableMagicMock, create_autospec

import pytest
from myrm_agent_harness.agent.skills.market.service import EnrichedSearchResult
from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult, SkillSearchResult

from app.core.skills.discovery.agent_market_install import (
    AgentSessionSkillMarketBackend,
    install_from_url_for_agent_session,
)
from app.core.skills.discovery.market_install_flow import MarketInstallFlowResult
from app.core.skills.discovery.mount import SkillMountResult
from app.core.skills.marketplace.market_service import SkillMarketService

_ADAPTER = "app.core.skills.discovery.agent_market_install"

_MOUNTED = SkillMountResult(mounted=True, agent_id="agent-1", mount_skill_id="prebuilt::demo")


def _flow_result(mount: SkillMountResult | None) -> MarketInstallFlowResult:
    return MarketInstallFlowResult(
        result=SkillInstallResult(success=True, skill_id="prebuilt::demo", skill_name="Demo"),
        mount_result=mount,
    )


def _market() -> NonCallableMagicMock:
    """Autospec of the real facade, so a call the facade does not accept fails here instead of in production."""
    market: NonCallableMagicMock = create_autospec(SkillMarketService, instance=True)
    return market


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


@pytest.fixture
def adoption(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The adoption bridge, isolated: left real it would reach the agent service and no assertion here would notice."""
    adopt = AsyncMock()
    monkeypatch.setattr(f"{_ADAPTER}.complete_discovery_adoption", adopt)
    return adopt


@pytest.fixture
def flow_by_id(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    flow = AsyncMock(return_value=_flow_result(_MOUNTED))
    monkeypatch.setattr(f"{_ADAPTER}.run_market_install_flow_by_id", flow)
    return flow


@pytest.fixture
def flow_from_url(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    flow = AsyncMock(return_value=_flow_result(_MOUNTED))
    monkeypatch.setattr(f"{_ADAPTER}.run_market_install_flow_from_url", flow)
    return flow


@pytest.mark.asyncio
async def test_install_delegates_to_flow(flow_by_id: AsyncMock, adoption: AsyncMock) -> None:
    out = await AgentSessionSkillMarketBackend(_market()).install("skill-a", "clawhub", user_id="u1")

    assert out.skill_id == "prebuilt::demo"
    flow_by_id.assert_awaited_once_with("skill-a", "clawhub", agent_id=None, mount_to_agent=True)
    adoption.assert_awaited_once_with("agent-1", "prebuilt::demo")


@pytest.mark.asyncio
async def test_install_from_url_delegates_to_flow(flow_from_url: AsyncMock, adoption: AsyncMock) -> None:
    out = await install_from_url_for_agent_session("https://github.com/o/r", None)

    assert out.skill_id == "prebuilt::demo"
    flow_from_url.assert_awaited_once_with("https://github.com/o/r", agent_id=None, mount_to_agent=True)
    adoption.assert_awaited_once_with("agent-1", "prebuilt::demo")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mount",
    [
        pytest.param(None, id="nothing-was-mounted"),
        pytest.param(replace(_MOUNTED, mounted=False), id="mount-did-not-succeed"),
        pytest.param(replace(_MOUNTED, mount_skill_id=""), id="no-mounted-skill-id"),
        pytest.param(replace(_MOUNTED, agent_id=""), id="no-agent"),
    ],
)
async def test_nothing_is_adopted_unless_a_skill_was_mounted_for_an_agent(
    flow_by_id: AsyncMock, adoption: AsyncMock, mount: SkillMountResult | None
) -> None:
    flow_by_id.return_value = _flow_result(mount)

    out = await AgentSessionSkillMarketBackend(_market()).install("skill-a", "clawhub")

    assert out.success
    adoption.assert_not_awaited()


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
