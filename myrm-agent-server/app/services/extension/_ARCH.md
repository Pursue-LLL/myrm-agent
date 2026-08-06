# services/extension/ 模块架构

## 架构概述

浏览器扩展桥服务层。管理 Chrome/Edge MV3 扩展的 WebSocket 连接，代理 CDP 供 Agent 浏览器自动化使用用户真实会话。实现 harness `ExtensionBridge` Protocol。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `ExtensionBridgeService`、`get_extension_bridge` | — |
| `bridge.py` | 核心 | WebSocket 生命周期、心跳、能力握手门禁（`hello.capabilities`）、浏览器连接、域名授权（`*.example.com` 匹配根域+子域）、域名策略告警分析、CDP 探测缓存、Wiki 剪藏 agent 推送（`clip_agent_update`） | ✅ |
| `clip_agent_config.py` | 核心 | UserConfig `extensionClipAgent` — WebUI 与 MV3 扩展 Wiki 剪藏 vault 范围 SSOT | ✅ |

## 设计要点

- **Playwright 单例**：`_ensure_playwright()` 跨连接复用实例，`disconnect()` 时释放。
- **域名授权**：`_match_domain()` 支持 `*.example.com` 匹配根域与子域；`connect_to_domain()` 与 `list_tabs()` 均经此过滤。
- **导航一致性**：`navigate_to_url()` 以 URL 主机为准做授权校验，并拒绝 `domain` 参数与 URL 主机不一致的请求，避免授权绕过。
- **能力握手门禁**：`hello` 带 `capabilities`（`navigate_url` / `list_tabs` / `attach_debugger` / `detach_debugger`）；`_send_request()` 对映射动作执行 capability 校验，并要求已完成 hello 握手。
- **握手可见性**：`ExtensionStatus.handshake_ready` 区分「WS 已连接」与「hello 已完成」，避免前端把同步窗口误判为能力缺失。
- **直连 CDP 风险治理**：`connect()` / `connect_to_domain()` 使用本地 CDP endpoint 时仅记录一次 WARNING，提示高权限路径需可信主机且禁止暴露 remote-debugging 端口。
- **策略告警**：`analyze_domain_policy_warnings()` 对 `*.example.com` 且未显式列出根域时返回结构化提示，避免无感放宽授权边界。
- **CDP 探测缓存**：`has_direct_cdp_endpoint()` 对“未发现”结果做短 TTL 负缓存，避免前端轮询 setup-hints 时重复高频探测。
- **认证**：WS 端点校验 `settings.extension_auth_token`（SecretStr）。
- **连接策略**：Extension 负责标签页选择与 debugger attach。私网导航只走 `navigate_url` 中继路径；当需要 Playwright BrowserInstance 时再复用主浏览器 CDP endpoint 建立 `connect_over_cdp` 连接。
- **SSE 状态广播**：连接/断开时通过 `ServerEventBus` 发布 `EXTENSION_STATUS_CHANGED` 事件，前端 NavBar 实时显示连接状态。
- **后台窗口隔离**：`_request_debugger_attach(background=True)` 默认指示 Extension 在非聚焦后台窗口中执行自动化，避免抢占用户焦点。
- **已登录 / 内网访问**：用户配置 Agent `browser_source=extension` 后，Agent 通过本桥接使用用户真实 Chrome 会话（登录态、Cookie），无需 OS 级 History/Bookmarks 读取。详见 harness `toolkits/browser/BROWSER_SYSTEM.md` §已登录站点与内网访问。

## 依赖

- PyPI `myrm-agent-harness` — `ExtensionBridge` Protocol、`BrowserInstance`
- `patchright.async_api`、`starlette.websockets`
- `app.services.event` — `AppEvent`、`AppEventType`、`get_event_bus`
