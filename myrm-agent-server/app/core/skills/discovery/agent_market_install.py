"""Chat agent skill_market_tool adapter onto unified market install flow.

[INPUT]
- app.core.skills.marketplace.market_service::SkillMarketService (POS: Business-layer market search with installed versions)
- app.core.skills.discovery.market_install_flow::run_market_install_flow_by_id (POS: Unified install)
- app.core.skills.discovery.market_install_flow::run_market_install_flow_from_url (POS: Unified URL install)
- app.core.skills.discovery.adopt::complete_discovery_adoption (POS: Discovery install adoption bridge)

[OUTPUT]
- AgentSessionSkillMarketBackend: SkillMarketBackend for chat turns (search unwraps hits, install runs the unified flow)
- install_from_url_for_agent_session: URL install callback for create_skill_market_tool

[POS]
Turn1 skill_market_tool uses the same install contract as Discover HTTP (replace snapshot, audit, mount, adopt).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult, SkillSearchResult

from app.core.skills.discovery.adopt import complete_discovery_adoption
from app.core.skills.discovery.market_install_flow import (
    MarketInstallFlowResult,
    run_market_install_flow_by_id,
    run_market_install_flow_from_url,
)

if TYPE_CHECKING:
    from app.core.skills.marketplace.market_service import SkillMarketService


async def _chat_adopt_after_mount(flow: MarketInstallFlowResult) -> None:
    mount_result = flow.mount_result
    if mount_result is not None and mount_result.mounted and mount_result.mount_skill_id and mount_result.agent_id:
        await complete_discovery_adoption(
            mount_result.agent_id,
            mount_result.mount_skill_id,
        )


class AgentSessionSkillMarketBackend:
    """SkillMarketBackend for chat turns: search unwraps market hits, installs run through market_install_flow."""

    __slots__ = ("_market",)

    def __init__(self, market: SkillMarketService) -> None:
        self._market = market

    async def search(self, query: str, limit: int = 10) -> list[SkillSearchResult]:
        return [hit.result for hit in await self._market.search(query, limit=limit)]

    async def install(
        self,
        skill_id: str,
        source: str,
        user_id: str | None = None,
    ) -> SkillInstallResult:
        del user_id
        flow = await run_market_install_flow_by_id(
            skill_id,
            source,
            agent_id=None,
            mount_to_agent=True,
        )
        await _chat_adopt_after_mount(flow)
        return flow.result


async def install_from_url_for_agent_session(url: str, user_id: str | None) -> SkillInstallResult:
    del user_id
    flow = await run_market_install_flow_from_url(
        url,
        agent_id=None,
        mount_to_agent=True,
    )
    await _chat_adopt_after_mount(flow)
    return flow.result
