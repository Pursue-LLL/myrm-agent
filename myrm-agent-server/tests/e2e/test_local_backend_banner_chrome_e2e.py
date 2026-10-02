"""Chrome E2E: local-backend banner 与连接切换改动的 WebUI 可达回归面。

覆盖 roadmap 项16（CrossDeviceAgentRosterAndMemorySyncPack）二轮修复包的
浏览器可达回归：
- AppLayout 挂载 LocalBackendUnavailableBanner：banner 模块 import 链路
  （含 switchRemoteFollow / toast）在真实浏览器真实加载，模块级错误会导致
  页面白屏、React bridge 失败。
- 后端 ready 时 banner 不显示（正常路径零回归）。
- /settings 页正常渲染：ServerConnectionCard 模块（SystemSection）在非
  Tauri 环境 return null 不崩溃。

Tauri 专属链路（switch_remote_follow Rust 编排、ServerConnectionCard 的
Tauri UI、banner 的 Tauri 分支）在纯 Chrome 结构性不可达：
isRemoteGatewayActive() = isTauriRuntime() && getRemoteGatewayConfig() !== null
（deploy-mode.ts），window.__TAURI__ 仅存在于 Tauri WebView。该链路的真实
代码级验证由 cargo test 覆盖（真实 Rust 编排，非 mock）。
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)

_BANNER_ABSENT_JS = """(async () => {
  return document.querySelector('[data-testid="local-backend-unavailable-banner"]') === null;
})()"""

_SETTINGS_RENDERED_JS = """(async () => {
  const text = document.body.innerText || '';
  return { rendered: text.trim().length > 100, length: text.trim().length };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_local_backend_banner_regression_chrome_e2e() -> None:
    """Verify connection-switch changes keep WebUI mount paths healthy."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(
            client,
            page,
            # 首次实测冷编译下 90s 预算超时（settings 路由 on-demand 编译 +
            # reload-heal），基础预算加倍覆盖冷启动；热态照常提前返回。
            timeout_sec=_warm_ui_parallel_wait_sec(180.0),
            page_url=f"{ui_url}/",
        )
        # AppLayout + banner 模块链路真实加载成功；后端 ready 时 banner 不显示。
        banner_absent = client.evaluate(page, _BANNER_ABSENT_JS)
        assert banner_absent is True, "banner must stay hidden while backend is ready"

    warm_ui_route("/settings")
    with open_mcp_page(f"{ui_url}/settings", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(180.0),
            page_url=f"{ui_url}/settings",
        )
        settings_state = client.evaluate(page, _SETTINGS_RENDERED_JS)
        assert settings_state.get("rendered") is True, (
            f"settings page must render with ServerConnectionCard module loaded: {settings_state}"
        )
