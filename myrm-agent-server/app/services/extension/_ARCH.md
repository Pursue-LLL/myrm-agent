# services/extension/ 模块架构

## 架构概述

浏览器扩展桥服务层：管理 Chrome MV3 扩展的 WebSocket 生命周期、心跳、CDP 命令代理与授权域名白名单；实现 harness `ExtensionBridge` Protocol，并在 warmup 注入 `GlobalBrowserPool` 供 `browser_source=extension` 复用用户真实会话。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 bridge 单例访问器 | — |
| `bridge.py` | 核心 | `ExtensionBridgeService`：WS 连接、CDP 代理、域名通配匹配、标签页枚举 | ✅ |

## 设计要点

- **Playwright 单例**：`_ensure_playwright()` 跨 CDP 连接复用同一 Playwright 实例，`disconnect()` 时释放。
- **域名通配**：`_match_domain()` 使用 `fnmatch`（如 `*.example.com`）；`connect_to_domain()` 与 `list_tabs()` 均经此过滤。
- **认证**：WebSocket `token` 对齐 `settings.extension_auth_token`（`api/extension/router.py` 校验）；REST `/extension/status` 返回 `token_required`（bool，不回传明文）。
- **池注入**：`lifecycle/browser.py` warmup 将单例注入 `GlobalBrowserPool`。

## 模块依赖

- `myrm_agent_harness.toolkits.browser.pool.extension_bridge` — Protocol 契约
- `myrm_agent_harness.toolkits.browser.pool.browser_launcher` — `BrowserInstance`
- `patchright.async_api` — CDP 驱动

## 对外入口

- HTTP/WS：[api/extension/_ARCH.md](../../api/extension/_ARCH.md)
- 客户端：[myrm-agent-extension/_ARCH.md](../../../../myrm-agent-extension/_ARCH.md)
