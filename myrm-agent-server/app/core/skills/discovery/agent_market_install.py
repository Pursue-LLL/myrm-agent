"""Chat agent skill_market_tool adapter onto unified market install flow.

[INPUT]
- app.core.skills.discovery.market_install_flow::run_market_install_flow_by_id (POS: Unified install)
- app.core.skills.discovery.market_install_flow::run_market_install_flow_from_url

[OUTPUT]
- wrap_skill_market_backend_for_agent_session: Proxy SkillMarketBackend for chat turns
- make_agent_session_install_from_url_fn: URL install callback for create_skill_market_tool

[POS]
Turn1 skill_market_tool uses the same install contract as Discover HTTP (replace snapshot, audit, mount, adopt).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.discovery.adopt import complete_discovery_adoption
from app.core.skills.discovery.market_install_flow import (
    MarketInstallFlowResult,
    run_market_install_flow_by_id,
    run_market_install_flow_from_url,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def _chat_adopt_after_mount(flow: MarketInstallFlowResult) -> None:
    mount_result = flow.mount_result
    if (
        mount_result is not None
        and mount_result.mounted
        and mount_result.mount_skill_id
        and mount_result.agent_id
    ):
        await complete_discovery_adoption(
            mount_result.agent_id,
            mount_result.mount_skill_id,
        )


class AgentSessionSkillMarketBackend:
    """SkillMarketBackend proxy: chat installs run through market_install_flow."""

    __slots__ = ("_inner",)

    def __init__(self, inner: object) -> None:
        self._inner = inner

    async def search(self, query: str, limit: int = 10):  # noqa: ANN201
        return await self._inner.search(query, limit=limit)

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

    async def get_detail(self, skill_id: str, source: str):  # noqa: ANN201
        return await self._inner.get_detail(skill_id, source)

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def wrap_skill_market_backend_for_agent_session(inner: object) -> AgentSessionSkillMarketBackend:
    return AgentSessionSkillMarketBackend(inner)


def make_agent_session_install_from_url_fn(
    inner: object,
) -> Callable[[str, str | None], Awaitable[SkillInstallResult]]:
    del inner

    async def install_from_url(url: str, user_id: str | None) -> SkillInstallResult:
        del user_id
        flow = await run_market_install_flow_from_url(
            url,
            agent_id=None,
            mount_to_agent=True,
        )
        await _chat_adopt_after_mount(flow)
        return flow.result

    return install_from_url
