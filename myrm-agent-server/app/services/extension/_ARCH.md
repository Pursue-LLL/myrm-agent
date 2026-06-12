# services/extension/ 模块架构

## 架构概述

浏览器扩展桥服务层。管理 Chrome/Edge MV3 扩展的 WebSocket 连接，代理 CDP 供 Agent 浏览器自动化使用用户真实会话。实现 harness `ExtensionBridge` Protocol。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `ExtensionBridgeService`、`get_extension_bridge` | — |
| `bridge.py` | 核心 | WebSocket 生命周期、心跳、CDP 代理、域名授权（`fnmatch` 通配） | ✅ |

## 设计要点

- **Playwright 单例**：`_ensure_playwright()` 跨连接复用实例，`disconnect()` 时释放。
- **域名授权**：`_match_domain()` 支持 `*.example.com`；`connect_to_domain()` 与 `list_tabs()` 均经此过滤。
- **认证**：WS 端点校验 `settings.extension_auth_token`（SecretStr）。
- **SSE 状态广播**：连接/断开时通过 `AppEventBus` 发布 `EXTENSION_STATUS_CHANGED` 事件，前端 NavBar 实时显示连接状态。

## 依赖

- PyPI `myrm-agent-harness` — `ExtensionBridge` Protocol、`BrowserInstance`
- `patchright.async_api`、`starlette.websockets`
- `app.services.event` — `AppEvent`、`AppEventType`、`get_event_bus`
