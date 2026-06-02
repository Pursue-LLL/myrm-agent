"""Browser pool configuration for application layer

按部署模式选择 `BrowserPoolConfig` 预设：
- 本地模式（LOCAL） → `BrowserPoolConfig.minimal()` + `LaunchMode.AUTO`（自动检测并连接系统 Chrome）
- Sandbox → `BrowserPoolConfig.defensive()` + `LaunchMode.LAUNCH`（沙箱内无系统 Chrome）

启动时通过 `get_browser_pool_config()` 取配置并传入 `GlobalBrowserPool`。
"""

import dataclasses
import os

from myrm_agent_harness.toolkits.browser.pool.config import (
    _DEFAULT_CDP_ENDPOINT,
    BrowserPoolConfig,
    LaunchMode,
)

from .deploy_mode import is_local_mode


def get_browser_pool_config() -> BrowserPoolConfig:
    """根据部署模式获取浏览器池配置

    本地模式: launch_mode=AUTO, 自动探测 CDP 连接已有 Chrome, fallback 到新启
    沙箱模式: launch_mode=LAUNCH, 始终新启 Chromium

    环境变量:
        CDP_PORT: 覆盖默认 CDP 端口 (默认 9222)

    Returns:
        对应部署模式下的 `BrowserPoolConfig` 实例
    """
    if is_local_mode():
        cdp_port = os.getenv("CDP_PORT")
        cdp_endpoint = f"http://127.0.0.1:{cdp_port}" if cdp_port else _DEFAULT_CDP_ENDPOINT

        base = BrowserPoolConfig.minimal()
        return dataclasses.replace(
            base,
            launch_mode=LaunchMode.AUTO,
            cdp_endpoint=cdp_endpoint,
        )

    return BrowserPoolConfig.defensive()


__all__ = ["get_browser_pool_config"]
