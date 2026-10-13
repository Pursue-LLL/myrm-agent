"""Post-install hooks for chat agent skill_market_tool (parity with Discover API).

[INPUT]
- myrm_agent_harness.backends.skills.market_protocols::SkillInstallResult
- app.ai_agents.general_agent.context::get_current_agent_id (POS: Active agent in chat turn)
- app.core.skills.discovery.mount::maybe_mount_after_install
- app.core.skills.discovery.adopt::complete_discovery_adoption

[OUTPUT]
- apply_agent_session_post_install: Catalog enable + optional allowlist adoption
- wrap_skill_market_backend_for_agent_session: Proxy backend with wrapped install
- make_agent_session_install_from_url_fn: URL install callback for create_skill_market_tool

[POS]
Discover ``install-from-url`` runs mount + adoption after install; chat Turn1 market tool did not.
This module mirrors that behavior using the current chat agent id from context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.discovery.adopt import complete_discovery_adoption
from app.core.skills.discovery.mount import maybe_mount_after_install

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def apply_agent_session_post_install(result: SkillInstallResult) -> None:
    """Enable installed skill in user catalog and adopt into explicit allowlist when applicable."""
    if not result.success:
        return

    from app.ai_agents.general_agent.context import get_current_agent_id

    mount_result = await maybe_mount_after_install(
        result,
        agent_id=get_current_agent_id(),
        mount_to_agent=True,
    )
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
    """Delegates to the business market service and runs Discover-equivalent post-install."""

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
        result = await self._inner.install(skill_id, source)
        await apply_agent_session_post_install(result)
        return result

    async def get_detail(self, skill_id: str, source: str):  # noqa: ANN201
        return await self._inner.get_detail(skill_id, source)

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def wrap_skill_market_backend_for_agent_session(inner: object) -> AgentSessionSkillMarketBackend:
    return AgentSessionSkillMarketBackend(inner)


def make_agent_session_install_from_url_fn(
    inner: object,
) -> Callable[[str, str | None], Awaitable[SkillInstallResult]]:
    async def install_from_url(url: str, user_id: str | None) -> SkillInstallResult:
        del user_id
        result = await inner.install_from_url(url)
        await apply_agent_session_post_install(result)
        return result

    return install_from_url
