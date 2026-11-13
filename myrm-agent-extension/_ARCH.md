# myrm-agent-extension 模块架构

## 架构概述

Chrome/Edge MV3 浏览器扩展。通过 WebSocket 连接本机 `myrm-agent-server`，代理 `chrome.debugger` 操作实现标签页管理与控制，使 Agent 可读取用户已授权标签页状态。同时提供 **Side Panel Chat UI**，让用户在浏览网页时可直接与 Agent 对话，无需切换窗口。

Server 侧见 `myrm-agent-server/app/api/extension/` 与 `app/services/extension/`；WebUI 管理见 Settings → `extensionBridge` Tab。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `manifest.json` | 核心 | MV3 清单：权限（含 `tabGroups`，用于「Myrm Agent」标签组标记；`webNavigation`，只用于认出 Agent 页面点开的新标签页由哪个标签页开出）、Service Worker、popup、side_panel；`default_locale` + `_locales/` 中英双语 | — |
| `src/i18n.js` | 辅助 | `msg()` / `applyDocumentI18n()` — Chrome `_locales` SSOT | ✅ |
| `_locales/en/messages.json` | 辅助 | 英文 UI 文案 | — |
| `_locales/zh_CN/messages.json` | 辅助 | 简体中文 UI 文案 | — |
| `src/background.js` | 核心 | Service Worker 入口（ES module）：仅生命周期。浏览器随时可能终止 worker 并以空内存重启，所以每次启动（安装、浏览器启动、闹钟、消息）都做同一套恢复：载入已存状态、释放上一个 worker 遗留的 debugger、清理已不存在的 Agent 标签页记录、确保保活闹钟存在、除非用户主动断开否则重连；其余逻辑在 `src/background/` | ✅ |
| `src/background/state.js` | 核心 | 唯一的可变运行时状态 `state`（连接、授权策略、已附加标签页、剪藏结果、Agent 标签页）与持久化：设置写 `chrome.storage.local`，Agent 标签页归属写 `chrome.storage.session`（跨 worker 重启、不跨浏览器会话；「由哪个 Agent 标签页开出」只在新页面刚出现时有用，不持久化）；`whenRestored` 由每个入口等待；连接常量与 `EXTENSION_CAPABILITIES`（含 `agent_tab_control`） | ✅ |
| `src/background/policy.js` | 核心 | 访问策略判定（纯函数，无 chrome API）：域名匹配、标签页/导航目标是否被授权、暂停标签页；vitest 经 `myrm-agent-frontend/src/lib/extension/__tests__/backgroundPolicy.test.ts` 覆盖 | ✅ |
| `src/background/transport.js` | 辅助 | 向服务端发消息（未连接则丢弃）与工具栏徽标 | ✅ |
| `src/background/connection.js` | 核心 | WebSocket 生命周期：连接、`hello` 握手、指数退避重连、断开（断开即释放全部 debugger） | ✅ |
| `src/background/server_messages.js` | 核心 | 服务端消息分发：`ping`、`set_domains`、`set_access_policy`、`clip_agent_update`、`relay`、`request`；relay/request 的失败回报给服务端而不抛出；标签页已不在授权站点上的拒绝（`TabNotAuthorizedError`）带 `code: tab_not_authorized` 回报，服务端据此放手整个页面 | ✅ |
| `src/background/access_policy.js` | 核心 | 应用并回报授权策略；策略收窄后立即释放不再被授权的标签页 | ✅ |
| `src/background/relay.js` | 核心 | 服务端 CDP relay 的指令：`attach`/`detach`/`cdp`/`createTab`/`closeTab`；每条指令都重新校验标签页与导航目标；`closeTab` 只关 Agent 自己打开的标签页（其余回报 `closed:false`）；Agent 自己的标签页可导航回空白页（浏览器工具箱丢弃被拒文档时这样做），用户的标签页不可；标签页已不在授权站点上时拒绝其后的每条 `cdp` 指令，并以 `TabNotAuthorizedError` 与普通失败区分 | ✅ |
| `src/background/actions.js` | 核心 | 服务端请求：`list_tabs`/`attach_debugger`/`navigate_url`/`detach_debugger` | ✅ |
| `src/background/tabs.js` | 核心 | 标签页读取（可操作、可列出、按域名查找、等待加载）与 `tabs_update` 推送；Agent 的标签页带 `agentOwned`，由 Agent 页面开出的另带 `openerTabId` | ✅ |
| `src/background/tab_events.js` | 辅助 | 标签页事件监听：Agent 页面点开新标签页时由 `webNavigation.onCreatedNavigationTarget` 的来源标签页认领并推送列表；导航/加载后推送列表；标签页关闭时清理已附加、暂停与 Agent 标签页记录 | ✅ |
| `src/background/debugger.js` | 核心 | `chrome.debugger` 的附加/释放与 CDP 事件回传；附加时回报浏览器自己的页面 target id（CDP 客户端按它匹配主框架）；`releaseStaleDebuggers` 释放上一个 worker 遗留的附加；后台窗口里的标签页随 debugger 一起关闭 | ✅ |
| `src/background/agent_tabs.js` | 核心 | Agent 自己打开的标签页：打开（用户窗口前台，或显式要求后台时用独立后台窗口）、记录归属并持久化、关闭；Agent 页面点开的新标签页也在这里认领（`adoptOpenedTab`，来源取自导航事件而非标签页自带的 `openerTabId`——后者是窗口里当前激活的标签页，Agent 在后台标签页里点击时指向用户的标签页；用户自己标签页开出的页面不认领；开往用户未授权站点的页面也不认领，Agent 看不到的页面不交给它；认领规则由 vitest 经 `myrm-agent-frontend/src/lib/extension/__tests__/agentTabs.test.ts` 覆盖）。只有这里登记的标签页能应服务端请求被关闭，用户的标签页永远不会被 Agent 关掉；策略在空白期放行 Agent 标签页，Agent 因此能把自己开的页面导航到所需站点；`pruneAgentTabs` 清理已不存在的记录 | ✅ |
| `src/background/tab_group.js` | 辅助 | 「Myrm Agent」标签组：让用户一眼看出 Agent 在哪些标签页里工作；同一窗口共用一个组、编辑串行。只是标记，不是访问边界（策略不读分组；用户取消分组或浏览器没有标签组 API 时行为不变） | ✅ |
| `src/background/background_window.js` | 辅助 | 不打扰用户的独立后台窗口：未聚焦创建、清理带内容的标签页；用户关闭窗口即遗忘；其中哪些标签页属于 Agent 由 `agent_tabs.js` 决定 | ✅ |
| `src/background/ui_messages.js` | 核心 | popup/Side Panel 的 `chrome.runtime.onMessage` 接口：`get_status`、`connect`、`disconnect`、`update_domains`、`update_access_policy`、`toggle_pause_tab`、`get_access_policy`、`glow_control` | ✅ |
| `src/background/clip.js` | 辅助 | Wiki clip 与 Service Worker 的衔接：同步剪藏目标 agent、提交剪藏、结果回写 `lastClipErrorKind` 并发 `chrome.notifications`；上传本身在 `src/wiki/*` | ✅ |
| `src/background/context_menu.js` | 辅助 | 右键菜单（`chrome.i18n`）与键盘快捷键：打开 Side Panel、剪藏页面/选区 | ✅ |
| `src/wiki/deep_links.js` | 辅助 | Settings Wiki 深链 builder | ✅ |
| `src/wiki/clip_client.js` | 核心 | Wiki clip REST 客户端；错误文案 `chrome.i18n` | ✅ |
| `src/wiki/` | 子模块 | Extension wiki clip 客户端与深链 — 见 [src/wiki/_ARCH.md](src/wiki/_ARCH.md) | ✅ |
| `src/popup.html` | 辅助 | Popup 结构；静态文案 `data-i18n` + 运行时 `applyDocumentI18n` | — |
| `src/popup.js` | 辅助 | Popup 控制器：连接状态；clip conflict/security/success 深链（`lastClipErrorKind` 结构化，非 regex）；审批提醒开关（`approvalNotifyEnabled`，默认开）；`chrome.i18n` 双语 | ✅ |
| `src/sidepanel/sidepanel.html` | 核心 | Side Panel 入口页面（ES module）：Chat UI 结构（SVG 图标、语义化 HTML）；界面与审批弹窗文案均 `data-i18n`；审批弹窗为 `role="alertdialog"`（`aria-labelledby` 标题、`aria-describedby` 明细） | — |
| `src/sidepanel/sidepanel.css` | 核心 | Side Panel 样式：暗色主题（文字与按钮对比度均不低于 WCAG AA 的 4.5:1）、消息气泡、工具进度、审批弹窗（随内容增高，高度上限为面板剩余高度 `100vh - 80px`，底边固定在输入区上方 `100vh - 70px`；只有明细列表滚动，按钮始终可见；列表边缘仅在其外还有内容时渐隐提示——滚动时间线取自列表自身，内容放得下时没有可滚动距离、时间线未激活，短列表因此不会渐隐）、流式指示器、输入区（审批待决时为虚线禁用态）、`prefers-reduced-motion: reduce` 全局守卫（面板是独立文档，宿主样式表的守卫到不了这里） | — |
| `src/sidepanel/sidepanel.js` | 核心 | Side Panel Chat 控制器：发送消息、渲染 SSE 事件、协调审批（展示、提醒、输入暂停、到期收起）并用 `resume_value` 恢复暂停的回合；loop guard 暂停（`approval_required` 且 `isLoopGuardPause`）不开审批卡、不锁输入、不提醒，只在回合里写一条「这一步连续失败、已停下」的说明；错误给本地化文案（服务端因上一回合仍在运行拒绝新消息时说明 Agent 仍在处理，其余为通用文案），细节只写控制台 | ✅ |
| `src/sidepanel/approval.js` | 核心 | 审批规则（纯函数，无 DOM/chrome）：`describeApproval`（白话说明、完整命令/参数、原因、截止时刻，以及能否在面板内批准）、`isLoopGuardPause`（loop guard 暂停无人可答，不是审批）、`resolveApprovalCopy`/`clockTimeFormatter`（本地化文案）、`buildResumeValue`/`buildStreamBody`（请求体同时声明面板的工具集）、`isResumeConflict`；vitest 经 `myrm-agent-frontend/src/lib/extension/__tests__` 覆盖 | ✅ |
| `src/sidepanel/approval_overlay.js` | 辅助 | 审批弹窗 DOM 渲染：逐项写入说明/命令/原因（一律 `textContent`）、截止行、提示；`focusSafeAnswer` 仅在面板已有焦点时把焦点给「拒绝」 | ✅ |
| `src/sidepanel/approval_notify.js` | 辅助 | 审批系统通知：窗口不在前台或面板不可见时提醒（不含命令正文），点击把窗口带回前台；同一 id 的通知互相替换，答复/取消/新会话时撤回 | ✅ |
| `src/sidepanel/chat_view.js` | 辅助 | 消息列表 DOM：用户/助手气泡、流式文本、工具行容器、中性提示（同一回合里相同的提示只显示一次）、错误气泡（`.error` 样式）、清空 | ✅ |
| `src/sidepanel/page_context.js` | 辅助 | 当前页签与选中文本的上下文条及查询前缀 | ✅ |
| `src/sidepanel/server_client.js` | 辅助 | 由 `serverUrl` 推导 HTTP 基址、带 Bearer token 的 `apiFetch`、健康检查状态（`disconnected`/`connecting`/`connected`/`error`），`serverUrl`/`authToken` 变更后自动重检 | ✅ |
| `src/sidepanel/sse.js` | 辅助 | `readSSE`：解析 agent SSE 流（`data:` 行、`[DONE]` 终止；坏行跳过、回调异常记录后继续） | ✅ |
| `src/sidepanel/tool_steps.js` | 辅助 | 工具进度行渲染：`addToolStep` / `updateLastToolStep`（工具名只作文本写入，不解析为 HTML）；vitest 经 `myrm-agent-frontend/src/lib/extension/__tests__` 覆盖 | ✅ |
| `src/content/selection.js` | 辅助 | Content Script（manifest 注入）：监听 mouseup 捕获用户选中文本，转发至 Side Panel | ✅ |
| `src/content/clip_image_urls.js` | 核心 | srcset/lazy/picture 图片 URL 解析（`MyrmClipImageUrls` SSOT） | ✅ |
| `src/content/clip.js` | 核心 | Content Script（动态注入）：捕获 page/selection HTML + credentialed 图片 fetch | ✅ |
| `src/content/glow.js` | 辅助 | Content Script（动态注入）：Agent 工作时在网页视口边缘显示发光效果 | ✅ |
| `icons/icon{16,32,48,128}.png` | 辅助 | 扩展图标（16/32/48/128） | — |

## 连接契约

| 项 | 说明 |
|----|------|
| WebSocket | `ws://<server>/api/v1/ws/extension?token=<extension_auth_token>` |
| 握手 | 扩展发送 `hello`（version、browser、capabilities=`navigate_url|list_tabs|attach_debugger|detach_debugger|agent_tab_control`）；Server 校验 `settings.extension_auth_token` 并按 capability 执行动作门禁 |
| 域名授权 | `authorizedDomains` / `allowAllEligibleTabs` / `pausedTabIds` 存于 `chrome.storage.local`；Server REST `/api/v1/extension/domains` 与 `/extension/access-policy` 与 WebUI 同步 |
| Relay 域名门禁 | `createTab`、`navigate_url`、relay `attach`/`cdp`（每次 tab URL recheck + `Page.navigate` 目标校验）共用 access policy；`closeTab` 只作用于 Agent 自己打开的标签页 |
| Agent 标签页 | Agent 开的标签页默认在用户窗口前台打开（后台标签页会被浏览器节流，登录态页面读不准）并归入「Myrm Agent」标签组；归属记录在 `chrome.storage.session`，关闭标签页即遗忘 |
| Worker 重启 | 浏览器可随时终止 service worker；每次启动先恢复已存状态、释放遗留 debugger，再按需重连（用户主动断开的除外，重连计时器不会撤销它） |
| Per-tab pause | WebUI「可用标签页」暂停/恢复；tab 关闭时 extension+server 自动 prune `paused_tab_ids`；`applyAccessPolicyPayload` 在 policy 变更（WebUI / popup / server push）后统一 detach 不再授权的 debugger |
| 配对 One-Shot | popup 粘贴 WebUI JSON bundle → `POST /extension/pairing/consume` → 自动 connect |
| 保活 | `chrome.alarms` 周期唤醒；断线指数退避重连 |

## Side Panel API 契约

Side Panel 通过 HTTP+SSE 直接与 server 通信（复用现有 chat API），**不** 经过 background.js 的 WebSocket：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/agents/agent-stream` | POST | 发送消息并接收 SSE 流式响应；每个请求都带 `agent_config.enabled_builtin_tools`（`web_search`、`memory`，不含 `structured_clarify`，见下文「Side Panel 工具集」）；带 `resume_value`（`{decision: "approve"}` 或 `{decision: "reject", feedback}`，审批事件带 `interruptId` 时一并回传）时答复该回合暂停中的工具审批并继续流式输出；审批已被超时或其他窗口处理时服务端返回 409 |
| `/api/v1/agents/agent/{messageId}/cancel` | POST | 取消当前执行 |
| `/api/v1/health` | GET | 连接状态检测 |
| `/api/v1/extension/clip-agent` | GET/PUT | Wiki 剪藏目标 agent + WebUI origin（与 Settings → Extension Bridge 同步） |
| `/api/v1/wiki/clip` | POST | 浏览器剪藏 multipart 上传（可选 `?agent_id=`；`folder_path=""` 默认月分目录；`queue_compile=false` 零 LLM） |

## Side Panel 审批边界

原回合的 SSE 在中断处结束；答复以同一 `message_id` / `chat_id` 发起新请求，续写的输出追加到同一条助手消息。

| 请求 | Side Panel 行为 |
|------|-----------------|
| `tool_approval_request`（普通） | 弹窗逐项展示：shell 命令为白话说明（harness 的 `plain_explanation`，按界面语言取 zh/en）+ 完整命令 + 策略原因；其他工具列出参数 + 原因；一律不显示内部工具名。底部一行「HH:MM:SS 前未处理将自动拒绝/允许」，按事件到达时刻加 `extensions.timeout.seconds` 在面板自己的时钟上算（服务端 `expiresAt` 的时钟浏览器不一定共用），`behavior` 决定措辞。一次批准/拒绝应用于该中断的全部动作；答复回传事件的 `interruptId`；弹窗一次只显示最后到达的一张 |
| shell 命令超过 2000 字符，或任一参数值超过 300 字符 | 展示被截断的内容并以 `…` 标明，只能拒绝：看不全的内容不批准，危险片段可能藏在被截去的部分 |
| 某个动作没有任何可展示内容（无说明、无参数、无原因） | 只能拒绝：不盲批 |
| `tool_approval_request` 且任一动作的 `reviewConfigs` 项带有 `allowedDecisions` / `hideAllowAlways` / `domainApproval` 之外的开启字段（如 `isSpend`、`requiresDualInsurance`、`irreversibleDestructive`、`smartDenied`、`batchImpactSummary`），或 `allowedDecisions` 不含 `approve`，或 `displayMode` 为 `handover` | 只能拒绝；批准须回 Web 端（Web 端有额外确认与信息展示，Side Panel 不绕过；未知新字段同样视为需要 Web 端，默认拒绝批准） |
| `approval_required` 等其他审批 | 仅提示去 Web 端处理，弹窗可忽略 |
| 答复请求未送达（网络失败、服务端错误） | 提示「答复没有送达」并让弹窗重新出现，可再次答复；用户取消或开新会话时不重现 |
| 答复请求返回 409（超时或已在别处处理） | 提示该审批已被处理，不再重试 |
| 截止时刻已过仍未答复 | 服务端此时自行处理（默认拒绝，`behavior` 为 `allow` 时批准）；弹窗收起并给出「审批已超时」的中性提示，输入框恢复；截止时间超过浏览器定时器上限（约 24.8 天）时不设定时器 |
| 服务端因该会话上一回合仍在运行拒绝新消息（SSE `error` 事件，`error_type` 为 `AgentBusyError`，或等价的 `status_code` 409；例如审批超时后服务端继续运行被暂停的回合，面板此时空闲） | 聊天里提示「Agent 还在处理上一步，请稍后再试」（错误样式），不显示通用的「检查连接」；输入框恢复，被拒绝的文字仍留在用户气泡里 |
| 审批待决期间的界面 | 弹窗为 `alertdialog`，默认焦点在「拒绝」（仅当面板此刻已有焦点，不从用户正在输入的网页抢走焦点）；输入框与发送暂停并提示先处理审批 |
| 浏览器窗口不在前台或面板不可见 | popup「审批提醒」开启（默认开）时发一条系统通知，不含命令正文；点击把窗口带回前台；答复、取消、新会话时撤回 |

「原因」一行是 harness 的英文策略文本，面板按原文展示，不翻译；其余文案均走 `chrome.i18n`。

## Side Panel 工具集

面板请求不挂载 `structured_clarify`：它的提问表单（`clarification_required` 中断）只有 Web UI 能回答，而面板没有渲染它的位置，Agent 一旦调用，面板的流在中断处结束且没有任何提示。面板的每个请求（新消息与审批答复）都带同一份 `agent_config.enabled_builtin_tools`（`web_search`、`memory`，即服务端默认工具集去掉 `structured_clarify`），Agent 因此用对话文字提问，用户在面板输入框回答；工具集在一个会话内不变。`agent_config` 的其余字段取默认值，与服务端在没有 `agent_config` 时的初值相同（`services/agent/params/models.py:54` 的 `AgentConfigRequest`）。这些 id 由服务端白名单校验，写错的 id 会让请求在到达 Agent 前被拒，不会静默降级。

## Wiki clip 产品默认

Extension `src/content/clip.js` 固定 `folder_path=""`、`queue_compile=false`：

- 空 `folder_path` → server/harness 写入 `raw/clips/{YYYY-MM}/web_{sha12(source_url)}.md`（URL 稳定路径）
- `queue_compile=false` → 剪藏不触发 LLM；用户在 WebUI Settings → Wiki 点击 Compile
- clip ingress：extension 上传图（srcset 最高分辨率 + credentialed fetch）+ server Track B 拉剩余远程 markdown 图片
- 同 `source_url` 再剪 → **conflict**（`RawConflictPolicy.FAIL`）→ popup/通知引导 Duplicate Review；非静默覆盖
- REST API 仍接受自定义 `folder_path` 与 `queue_compile=true`（高级/集成调用）

Settings → Extension Bridge 仅配置 **Wiki clip target agent**（`/extension/clip-agent` SSOT）。

## Extension i18n 范围

| 表面 | 语言 | 机制 |
|------|------|------|
| Popup + clip 错误 + 右键剪藏菜单 + clip 系统通知 | en / zh_CN | `_locales` + `chrome.i18n` |
| Side Panel 审批弹窗、审批系统通知、popup 审批提醒开关 | en / zh_CN | `_locales` + `chrome.i18n`（`approval*` / `notifyApproval*` 键） |
| Side Panel Chat 界面（标题栏提示、空状态、输入框、思考/工具提示、错误提示） | en / zh_CN | `_locales` + `chrome.i18n`（`panel*` 键）；错误只给本地化文案，细节写控制台 |
| Side Panel 内的 Agent 回复、工具进度行里的工具名 | server 输出 | 回复语言由 server/WebUI 设置决定；工具进度行仍按原名显示 |
| WebUI Settings → Extension Bridge | 六语 | `myrm-agent-frontend` next-intl |

**Degraded deep links:** When `web_ui_origin` is not yet seeded from WebUI, clip still writes to Wiki; popup shows a success hint (`clipSavedWithoutOrigin`) until origin syncs.

认证通过 `Authorization: Bearer <authToken>`（从 `chrome.storage.local` 读取）。跨域请求由 `host_permissions: ["<all_urls>"]` 授权。

## 模块依赖

- **上游**：`myrm-agent-server` Extension Bridge（`ExtensionBridgeService` + harness `ExtensionBridge` Protocol）+ Chat API（`general_agent/streaming.py`）
- **下游**：无（终端用户浏览器）

## 安装

开发者模式加载 unpacked 扩展目录；在 popup 或 WebUI Settings → Browser Extension 配置 Server URL 与 Token。Side Panel 通过右键菜单 "Ask Myrm Agent"、键盘快捷键 Cmd+Shift+M、或点击扩展图标后在 Side Panel 中打开。
