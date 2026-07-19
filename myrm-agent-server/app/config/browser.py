"""Browser pool configuration for application layer

[INPUT] myrm_agent_harness.toolkits.browser.pool.config::BrowserPoolConfig (POS: 浏览器池配置数据结构)
[INPUT] app.schemas.config::BrowserCloudProviderConfigValue (POS: 云浏览器供应商配置模型)
[INPUT] app.services.config.service::config_service (POS: 配置持久化服务)
[OUTPUT] get_browser_pool_config: 根据部署模式生成 BrowserPoolConfig
[OUTPUT] get_browser_launch_options: 本地/沙箱 fallback 启动参数
[OUTPUT] resolve_cloud_browser_endpoint: 异步解析云浏览器 WS endpoint
[POS] 浏览器池配置工厂。按部署模式（Local/Sandbox）生成 BrowserPoolConfig 预设，支持注入云浏览器 endpoint。
"""

import dataclasses
import logging
import os

from myrm_agent_harness.toolkits.browser.pool.config import (
    _DEFAULT_CDP_ENDPOINT,
    BrowserPoolConfig,
    LaunchMode,
)

from .deploy_mode import is_local_mode

logger = logging.getLogger(__name__)


def _resolve_local_cdp_endpoint() -> str:
    """Resolve loopback CDP HTTP endpoint for local/connect browser modes."""
    cdp_port = os.getenv("CDP_PORT") or os.getenv("MYRM_CHROME_E2E_PORT")
    if cdp_port:
        return f"http://127.0.0.1:{cdp_port}"

    try:
        from myrm_agent_harness.toolkits.browser.pool.chrome_discovery import discover_chrome_cdp_endpoint

        discovered = discover_chrome_cdp_endpoint()
        if discovered:
            logger.info("Local CDP endpoint discovered: %s", discovered)
            return discovered
    except Exception:
        logger.debug("Local CDP discovery failed; falling back to default endpoint", exc_info=True)

    return _DEFAULT_CDP_ENDPOINT


async def resolve_cloud_browser_endpoint() -> str | None:
    """Read cloud browser provider config from database and resolve WS endpoint.

    Returns the WebSocket CDP URL if cloud browser is configured and enabled, None otherwise.
    """
    try:
        from app.schemas.config import BrowserCloudProviderConfigValue
        from app.services.config.service import config_service

        record = await config_service.get("browserCloudProvider")
        if not record:
            return None

        config = BrowserCloudProviderConfigValue.model_validate(record.value)
        endpoint = config.resolve_ws_endpoint()
        if endpoint:
            logger.info("Cloud browser endpoint resolved: provider=%s", config.provider)
        return endpoint
    except Exception:
        logger.debug("Cloud browser config not available (first run or no config)")
        return None


def get_browser_pool_config(*, remote_ws_endpoint: str | None = None) -> BrowserPoolConfig:
    """根据部署模式获取浏览器池配置

    本地模式: launch_mode=AUTO, 自动探测 CDP 连接已有 Chrome, fallback 到新启
    沙箱模式: launch_mode=LAUNCH, 始终新启 Chromium

    Args:
        remote_ws_endpoint: Optional cloud browser WebSocket endpoint (pre-resolved).

    环境变量:
        CDP_PORT: 覆盖默认 CDP 端口 (默认 9222)

    Returns:
        对应部署模式下的 `BrowserPoolConfig` 实例
    """
    if is_local_mode():
        cdp_endpoint = _resolve_local_cdp_endpoint()

        base = BrowserPoolConfig.minimal()
        return dataclasses.replace(
            base,
            launch_mode=LaunchMode.AUTO,
            cdp_endpoint=cdp_endpoint,
            remote_ws_endpoint=remote_ws_endpoint,
        )

    base = BrowserPoolConfig.defensive()
    if remote_ws_endpoint:
        return dataclasses.replace(base, remote_ws_endpoint=remote_ws_endpoint)
    return base


def get_browser_launch_options() -> dict[str, object]:
    """Launch options for GlobalBrowserPool fallback browser launch.

    Local mode uses a visible window when AUTO falls back to launching Chromium.
    Sandbox mode keeps the default headless launch (unless VISUAL_DESKTOP=1).
    """
    from myrm_agent_harness.toolkits.browser.pool.browser_pool import _DEFAULT_LAUNCH_OPTIONS

    options = dict(_DEFAULT_LAUNCH_OPTIONS)
    if is_local_mode():
        options["headless"] = False
    return options


__all__ = ["get_browser_pool_config", "get_browser_launch_options", "resolve_cloud_browser_endpoint"]
