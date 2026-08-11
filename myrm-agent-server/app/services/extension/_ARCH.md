# services/extension/ 模块架构

## 架构概述

浏览器扩展桥服务层。管理 Chrome/Edge MV3 扩展的 WebSocket 连接，代理 CDP 供 Agent 浏览器自动化使用用户真实会话。实现 harness `ExtensionBridge` Protocol。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `ExtensionBridgeService`、`get_extension_bridge` | — |
| `access_policy.py` | 核心 | 统一 tab 访问策略评估（domain 白名单 / allow-all / pause / internal URL 过滤） | ✅ |
| `bridge.py` | 核心 | WebSocket 生命周期、心跳、能力握手门禁、**CDP relay 编排**、浏览器连接、域名授权、CDP 探测缓存、Wiki 剪藏 agent WS 推送（`clip_agent_update`） | ✅ |
| `pairing.py` | 辅助 | 一次性 WebUI ↔ 扩展配对码 + consume rate limit | ✅ |
| `cdp_relay/` | 子包 | loopback DevTools façade + Target 合成 — 见 [cdp_relay/_ARCH.md](cdp_relay/_ARCH.md) | ✅ |
| `clip/` | 子包 | Wiki clip UserConfig SSOT — 见 [clip/_ARCH.md](clip/_ARCH.md) | ✅ |

## 设计要点

- **Playwright 单例**：`_ensure_playwright()` 跨连接复用实例，`disconnect()` 时释放。
- **域名授权**：`_match_domain()` / `access_policy.py` 支持 `*.example.com`；`list_tabs()`、`_sync_relay_tabs()`、relay attach **共用同一 filter**（fail-closed；空 domain 不再隐式全开）。
- **Allow-all 模式**：`allow_all_eligible_tabs` 显式开关；可与 per-tab `paused_tab_ids` 组合；关闭 tab 时 prune pause（Chrome tabId 复用）。
- **真实 automation 探针**：`relay_cdp_ready` 经 loopback `Browser.getVersion` 往返验证，且要求 access policy valid。
- **导航一致性**：`navigate_to_url()` 以 URL 主机为准做授权校验，并拒绝 `domain` 参数与 URL 主机不一致的请求，避免授权绕过。
- **能力握手门禁**：`hello` 带 `capabilities`（`navigate_url` / `list_tabs` / `attach_debugger` / `detach_debugger`）；`_send_request()` 对映射动作执行 capability 校验，并要求已完成 hello 握手。
- **握手可见性**：`ExtensionStatus.handshake_ready` 区分「WS 已连接」与「hello 已完成」，避免前端把同步窗口误判为能力缺失。
- **Extension 模式 fail-closed**：`connect()` / `connect_to_domain()` 仅经 CDP relay；relay 未就绪时拒绝连接，不 fallback 本地 direct CDP（避免绕过 domain policy）。
- **策略告警**：`analyze_domain_policy_warnings()` 对 `*.example.com` 且未显式列出根域时返回结构化提示，避免无感放宽授权边界。
- **CDP 探测缓存**：`has_direct_cdp_endpoint()` 对“未发现”结果做短 TTL 负缓存，避免前端轮询 setup-hints 时重复高频探测。
- **配对 One-Shot**：`POST /extension/pairing` 返回 `http_base` + `consume_url`；`POST /extension/pairing/consume` 交换一次性 ticket；扩展 popup 粘贴 bundle 后自动 connect。
- **认证**：WS 端点校验 `settings.extension_auth_token`（SecretStr）。
- **连接策略**：Extension 负责标签页选择与 debugger attach。Playwright 经 **CDP relay**（loopback `/json` façade + extension WS 隧道）连接；**extension 模式 fail-closed**，relay 未就绪时不 fallback 本地 direct CDP（避免绕过 domain policy）。`setup-hints.cdp_endpoint_discovered` 仍提示直连风险供 AUTO/CONNECT 模式参考。
- **SSE 状态广播**：连接/断开时通过 `ServerEventBus` 发布 `EXTENSION_STATUS_CHANGED` 事件，前端 NavBar 实时显示连接状态。
- **前台 tab 优先**：`_request_debugger_attach(background=False)` 为登录态场景默认；后台隔离窗仅显式请求时使用。
- **Relay 域名门禁**：扩展层对 `createTab`、`navigate_url`、relay `cdp`（tab URL recheck + `Page.navigate`）共用 access policy；server relay sync 与 list_tabs 同一规则。
- **已登录 / 内网访问**：用户配置 Agent `browser_source=extension` 后，Agent 通过本桥接使用用户真实 Chrome 会话（登录态、Cookie），无需 OS 级 History/Bookmarks 读取。详见 harness `toolkits/browser/BROWSER_SYSTEM.md` §已登录站点与内网访问。

## 依赖

- PyPI `myrm-agent-harness` — `ExtensionBridge` Protocol、`BrowserInstance`
- `patchright.async_api`、`starlette.websockets`
- `app.services.event` — `AppEvent`、`AppEventType`、`get_event_bus`
- `app.services.extension.clip` — Wiki clip agent UserConfig SSOT
