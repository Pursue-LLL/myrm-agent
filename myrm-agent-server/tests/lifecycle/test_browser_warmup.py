"""The warmed-up browser pool is created with the egress guard of the deployment.

The pool is a process singleton and its first creation wins, so the warmup path has to carry the same guard as every
other way of creating it, or the connection-level network policy would depend on which of them ran first.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.lifecycle.browser import warmup_global_browser_pool

_CREATE_POOL = "myrm_agent_harness.toolkits.browser.pool.get_global_browser_pool"


async def test_the_pool_is_created_with_the_guard_of_the_deployment() -> None:
    guard = MagicMock(name="guard")
    pool = MagicMock()
    pool.warmup = AsyncMock()

    with (
        patch("app.config.browser.get_browser_egress_guard", return_value=guard),
        patch("app.config.browser.resolve_cloud_browser_endpoint", AsyncMock(return_value=None)),
        patch("app.lifecycle.browser.resolve_browser_proxy_pool", AsyncMock(return_value=None)),
        patch("app.core.security.browser_vault.get_global_session_vault", return_value=MagicMock()),
        patch("myrm_agent_harness.toolkits.web_fetch.web_fetch_tools.set_session_vault"),
        patch("myrm_agent_harness.toolkits.browser.pool.singleton._global_pool", None),
        patch(_CREATE_POOL, return_value=pool) as create_pool,
    ):
        await warmup_global_browser_pool()

    assert create_pool.call_args.kwargs["egress_guard"] is guard
    pool.warmup.assert_awaited_once()
