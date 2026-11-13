# services/extension/ 模块架构

## 架构概述

浏览器扩展桥服务层。管理 Chrome/Edge MV3 扩展的 WebSocket 连接，代理 CDP 供 Agent 浏览器自动化使用用户真实会话。实现 harness `ExtensionBridge` Protocol。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `ExtensionBridgeService`、`get_extension_bridge` | — |
| `access_policy.py` | 核心 | 统一 tab 访问策略评估（domain 白名单 / allow-all / pause / internal URL 过滤） | ✅ |
| `bridge/` | 核心 | 扩展桥，按职责分 6 个 mixin（connection / access / relay / tabs / capability / clip_config）+ `state`（会话状态与 mixin 互调的类型声明）+ `service`（组合）+ `factory`（单例）+ `common`（常量、状态广播、relay manager、harness 契约类型出口）：WebSocket 生命周期与心跳、能力握手门禁、CDP relay 编排、浏览器连接、域名授权、CDP 探测缓存、Wiki 剪藏 agent 推送。见 [bridge/_ARCH.md](bridge/_ARCH.md) | ✅ |
| `pairing.py` | 辅助 | 一次性 WebUI ↔ 扩展配对码 + consume rate limit | ✅ |
| `relay_check.py` | 辅助 | Browser Doctor 的 `extension_relay` 检查：进程内读取 bridge 的连接/访问策略/relay 状态（不经 HTTP 自探测），映射为 `DoctorCheckResult`；未连接是可选能力（`details.optional`），已连接但无授权站点、server 缺 token 是需处理的告警；由 `/health/browser/doctor` 作为 `run_doctor(extra_checks=...)` 传入，harness 不认识本 server 的 relay | ✅ |
| `cdp_relay/` | 子包 | loopback DevTools façade + Target 合成 — 见 [cdp_relay/_ARCH.md](cdp_relay/_ARCH.md) | ✅ |
| `clip/` | 子包 | Wiki clip UserConfig SSOT — 见 [clip/_ARCH.md](clip/_ARCH.md) | ✅ |

## 设计要点

- **Playwright 单例**：`_ensure_playwright()` 跨连接复用实例，`disconnect()` 时释放。
- **域名授权**：`_match_domain()` / `access_policy.py` 支持 `*.example.com`；`list_tabs()`、`_sync_relay_tabs()`、relay attach **共用同一 filter**（fail-closed；空 domain 不再隐式全开）。
- **Allow-all 模式**：`allow_all_eligible_tabs` 显式开关；可与 per-tab `paused_tab_ids` 组合；关闭 tab 时 prune pause（Chrome tabId 复用）。
- **真实 automation 探针**：`relay_cdp_ready` 经 loopback `Browser.getVersion` 往返验证，且要求 access policy valid。
- **导航一致性**：`navigate_to_url()` 以 URL 主机为准做授权校验，并拒绝 `domain` 参数与 URL 主机不一致的请求，避免授权绕过。
- **能力握手门禁**：`hello` 带 `capabilities`（`navigate_url` / `list_tabs` / `agent_tab_control`，后者是 relay 开关标签页所需的能力）；`_send_request()` 对映射动作执行 capability 校验，并要求已完成 hello 握手。
- **握手可见性**：`ExtensionStatus.handshake_ready` 区分「WS 已连接」与「hello 已完成」，避免前端把同步窗口误判为能力缺失。
- **策略归属**：用户经 API 设过访问策略后，服务端的策略就是扩展必须持有的那份：握手时推送，扩展握手后立即回报的那份（`access_policy_update` 带 `initial: true`，是它在听到服务端之前保存的）被忽略。用户没设过（服务重启后内存是空的）则采用扩展保存的那份，所以重启不会清空扩展里的授权站点与暂停的标签页，两端也不会在重连时互换列表。连上之后扩展回报的改动（不带 `initial` 的回报）始终采用。已知边界：扩展离线期间在弹窗里改的策略，会被服务端已设的策略取代（要保留需要给策略带修订号，目前不做）。
- **Extension 模式 fail-closed**：`connect()` 仅经 CDP relay；relay 未就绪时拒绝连接，不 fallback 本地 direct CDP（避免绕过 domain policy）。
- **策略告警**：`analyze_domain_policy_warnings()` 对 `*.example.com` 且未显式列出根域时返回结构化提示，避免无感放宽授权边界。
- **CDP 探测缓存**：`has_direct_cdp_endpoint()` 对“未发现”结果做短 TTL 负缓存，避免前端轮询 setup-hints 时重复高频探测。
- **配对 One-Shot**：`POST /extension/pairing` 返回 `http_base` + `consume_url`；`POST /extension/pairing/consume` 交换一次性 ticket；扩展 popup 粘贴 bundle 后自动 connect。
- **认证**：WS 端点校验 `settings.extension_auth_token`（SecretStr）。
- **连接策略**：Extension 负责标签页选择与 debugger attach。Playwright 经 **CDP relay**（loopback `/json` façade + extension WS 隧道）连接；**extension 模式 fail-closed**，relay 未就绪时不 fallback 本地 direct CDP（避免绕过 domain policy）。`setup-hints.cdp_endpoint_discovered` 仍提示直连风险供 AUTO/CONNECT 模式参考。
- **SSE 状态广播**：连接/断开时通过 `ServerEventBus` 发布 `EXTENSION_STATUS_CHANGED` 事件，前端 NavBar 实时显示连接状态。
- **前台 tab 优先**：Playwright 新开的页面默认在用户窗口前台打开并归入「Myrm Agent」标签组；私网 `navigate_url` 默认在后台窗口的空白标签页里进行。用户的焦点窗口与当前标签页只在这一刻变化：relay 对 `Page.bringToFront`（Agent 的 switch_tab 会发）只应答不转发，转发会让 Chrome 激活该标签页并把整个窗口拉到最前，把用户从别的窗口或应用里拽出来；Agent 当前在哪个标签页是客户端自己的记录，不需要浏览器配合。
- **Agent 只关自己开的标签页**：`Target.createTarget` → 扩展 `createTab`（登记归属）；`Target.closeTarget` → 扩展 `closeTab`，Agent 的标签页真正关闭，用户的标签页只被放开（扩展回报 `closed:false`，relay 照样 detach 并遗忘，避免 Playwright 等 detach 而挂起）。扩展在标签页列表里以 `agentOwned` 标注 Agent 的标签页；server 把 Agent 自己开的空白标签页放进 relay 的标签页镜像（`bridge/access.py::_is_blank_agent_tab`，Agent 才能把它导航到所需站点），但 `list_tabs` 仍只按授权策略过滤，这些标签页不会被当作用户的标签页列出。
- **Agent 页面点开的新标签页也是 Agent 的**：Agent 的页面里点链接（`target=_blank`）或脚本 `window.open` 开出的标签页，由扩展依据 `webNavigation.onCreatedNavigationTarget` 带来的来源标签页认领（`agent_tabs.js::adoptOpenedTab`）：登记归属，并在标签页列表里以 `openerTabId` 标出由哪个 Agent 标签页开出（server 的 `_agent_tabs` 记「标签页 → 开出它的 Agent 标签页」，Agent 自己开的为 `None`）。不用标签页自带的 `openerTabId`：浏览器把窗口里当前激活的标签页填在那里，Agent 在后台标签页里点击时它指向用户的标签页（Agent 看不到自己点出来的页面），用户在后台标签页里点击时它指向 Agent 的标签页（把用户开的页面当成 Agent 的）。relay 见到「来源标签页已附加」的新标签页，就像 Chrome 的自动附加：附加它，并向已拿到来源页面的客户端通告 `Target.attachedToTarget`（带 `openerId`，沿用来源页面的虚拟上下文），Playwright 据此触发 `popup` 事件，harness 的 `TabController` 把新页面接成会话的当前标签页；关闭它真正关闭标签页，关闭虚拟上下文时一并关闭。桥只在新页面有了文档（URL 不再空白）后才把 opener 交给 relay：还空白的页面可能在客户端初始化到一半时就去了未授权站点，扩展随后会拒绝客户端的指令。用户自己的标签页开出的页面不是 Agent 的（谁点的无从判断），不认领也不通告；开往未授权站点的页面扩展不认领（`adoptOpenedTab` 看目的地）；经重定向才到那里的页面落地前一直空白、桥不交出，落地后按上一条「自行跳出授权域名」处理。
- **一个会话一条连接**：`connect()` 返回 `ExtensionBrowserInstance`（harness 契约类型）；池据此把同一浏览器的后续请求交给同一实例，给其上下文不加任何覆盖，也不让页面空闲留存，所以会话里关掉的标签页就是在用户浏览器里关掉。
- **扩展丢失即清场**：扩展断开时 relay 向 CDP 客户端通告全部目标消失、清空标签页镜像并让待决命令失败；重连后从零开始。
- **Relay 域名门禁**：扩展层对 `createTab`、`navigate_url`、relay `cdp`（tab URL recheck + `Page.navigate`）共用 access policy；server relay sync 与 list_tabs 同一规则（Agent 自己开的空白标签页除外，见上）。
- **自行跳出授权域名即摘离**：Agent 的页面被页面脚本或重定向带到未授权域名时，扩展对每条命令复核标签页当前地址，其后所有命令都失败，标签页也随之从列表消失，relay 通告目标已走（Playwright 侧页面即「已关闭」），内容读不到；跳转首包的 URL 与状态码仍会作为事件到达客户端。该标签页留在用户浏览器里，不替用户猜着关闭（可能正有人在里面完成登录），也不随会话结束而关闭。
- **文档先由 harness 在服务端取回**：生产会话里 harness 的文档注入路由（`enhancers/inject_route.py`）对每个 HTML 文档请求先在驱动侧发起一次取回（走服务端所在机器的网络，带着浏览器上下文里的 cookie），再把响应交给浏览器，取回失败才回落给浏览器自己加载。服务端与浏览器在同一台机器、双方解析到同一主机时无感；只有浏览器自己解析或到达的主机（浏览器独有的解析规则、代理、客户端证书）要先等这次取回失败才能回落：解析直接失败几乎无感，挂住（例如把任意域名映射成假地址的代理工具）会让导航等到取回失败，可能超过 15 秒的导航上限。服务端与浏览器不在同一台机器的拓扑尚未覆盖：那时这次取回从服务端的网络发出。
- **已登录 / 内网访问**：用户配置 Agent `browser_source=extension` 后，Agent 通过本桥接使用用户真实 Chrome 会话（登录态、Cookie），无需 OS 级 History/Bookmarks 读取。详见 harness `toolkits/browser/BROWSER_SYSTEM.md` §已登录站点与内网访问。

## 依赖

- `myrm-agent-harness`（本仓库 `../myrm-agent-harness`，可编辑路径源）— `ExtensionBridge` Protocol、`ExtensionBrowserInstance`
- `patchright.async_api`、`starlette.websockets`
- `app.services.event` — `AppEvent`、`AppEventType`、`get_event_bus`
- `app.services.extension.clip` — Wiki clip agent UserConfig SSOT
