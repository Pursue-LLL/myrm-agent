"""Browser lifecycle management — global pool warmup/shutdown, proxy pool resolution, expired session cleanup."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.pool.proxy import RoundRobinProxyPool

logger = logging.getLogger(__name__)


async def resolve_browser_proxy_pool() -> RoundRobinProxyPool | None:
    """Resolve browser proxy pool from DB config or MYRM_PROXIES env var.

    Priority: DB config (GUI) > MYRM_PROXIES environment variable.
    """
    from myrm_agent_harness.toolkits.browser.pool.proxy import RoundRobinProxyPool

    try:
        from app.schemas.config import BrowserProxyConfigValue
        from app.services.config.service import config_service

        record = await config_service.get("browserProxy")
        if record:
            proxy_config = BrowserProxyConfigValue.model_validate(record.value)
            if proxy_config.enabled and proxy_config.proxies:
                pool = RoundRobinProxyPool.from_urls(proxy_config.proxies)
                logger.info(
                    "Browser proxy pool loaded from config: %d proxies",
                    len(proxy_config.proxies),
                )
                return pool
    except Exception:
        logger.debug("Browser proxy config not available (first run or no config)")

    proxy_csv = os.getenv("MYRM_PROXIES", "")
    if proxy_csv:
        env_pool = RoundRobinProxyPool.from_csv(proxy_csv)
        if env_pool:
            logger.info("Browser proxy pool loaded from MYRM_PROXIES env var")
            return env_pool

    return None


async def warmup_global_browser_pool() -> None:
    """预热全局浏览器池（预创建 Browser 实例和 Page）"""
    from myrm_agent_harness.toolkits.browser.pool import get_global_browser_pool
    from myrm_agent_harness.toolkits.browser.pool import singleton as pool_singleton
    from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools

    from app.config.browser import (
        get_browser_launch_options,
        get_browser_pool_config,
        resolve_cloud_browser_endpoint,
    )
    from app.config.settings import settings
    from app.core.security.browser_vault import get_global_session_vault
    from app.services.extension.bridge import get_extension_bridge

    if pool_singleton._global_pool is not None:
        await pool_singleton._global_pool.shutdown()
        pool_singleton._global_pool = None

    web_fetch_tools.set_session_vault(get_global_session_vault())

    cloud_endpoint = await resolve_cloud_browser_endpoint()
    config = get_browser_pool_config(remote_ws_endpoint=cloud_endpoint)
    launch_options = get_browser_launch_options()
    proxy_pool = await resolve_browser_proxy_pool()
    pool = get_global_browser_pool(
        max_browsers=settings.browser_pool.max_browsers,
        config=config,
        launch_options=launch_options,
        extension_bridge=get_extension_bridge(),
        proxy_pool=proxy_pool,
    )
    await pool.warmup(
        browsers=settings.browser_pool.warmup_browsers,
        pages_per_context=settings.browser_pool.warmup_pages,
    )
    logger.info(
        "GlobalBrowserPool warmup completed (proxy=%s)",
        "enabled" if proxy_pool else "disabled",
    )


async def shutdown_global_browser_pool() -> None:
    """关闭全局浏览器池"""
    from myrm_agent_harness.toolkits.browser.pool import get_global_browser_pool

    pool = get_global_browser_pool()
    await pool.shutdown()
    logger.info("[Shutdown] GlobalBrowserPool closed")


async def cleanup_expired_browser_sessions() -> None:
    """Clean up expired saved browser sessions from all vaults (global + per-agent)."""
    try:
        from app.core.security.browser_vault import (
            cleanup_all_agent_vaults,
            get_global_session_vault,
        )

        vault = get_global_session_vault()
        removed = await vault.cleanup_expired()

        agent_removed = await cleanup_all_agent_vaults()
        total_removed = removed + agent_removed

        if total_removed > 0:
            logger.info(
                "Cleaned up %d expired browser sessions (global=%d, agents=%d)",
                total_removed,
                removed,
                agent_removed,
            )
    except Exception as exc:
        logger.error("Expired session cleanup failed: %s", exc, exc_info=True)
