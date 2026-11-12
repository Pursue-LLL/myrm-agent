# api/remote_access/ 模块架构

## 架构概述

远程访问 HTTP 入口：CF quick tunnel 启停、Tailscale 状态探测、E2EE 握手、移动端 Pairing Token 签发、Mobile Hub 会话查询、节点事件接收。业务与安全逻辑见 [app/remote_access/_ARCH.md](../../remote_access/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `router.py` | 路由 | `/api/v1/remote-access/*` REST 核心端点与子路由挂载 | ✅ |
| `schemas.py` | 契约 | 远程访问请求/响应 Pydantic 模型（Pairing Token、E2EE 握手、tunnel 启动、远程新建会话、节点事件） | ✅ |

## 端点

- `GET /tailscale/status` — Tailscale 守护进程探测、IP、MagicDNS 域名与一键配置状态
- `GET|POST /tunnel/*` — tunnel 状态与生命周期
- `GET /e2ee/public-key` — daemon 公钥（QR URL fragment `#e2ee=`）
- `POST /e2ee/handshake` — `e2ee_hello` → `e2ee_ready` + sessionId
- `POST /pairing-token` — WebUI session 签发 Hub list token；list pair upgrade **存在 chat**（运行中或已完成，回收站排除）scoped token；支持 `browser_takeover` purpose 并返回 `mobilePath/mobileUrl`
- `POST /pairing-token/refresh` — pair token 续期（Hub list / scoped 控制 / browser takeover），返回续期后的 `mobilePath/mobileUrl`
- `GET /mobile/sessions` — 进行中 Agent 会话（含 agentName）+ 最近完成会话（recentSessions ≤10，排除回收站与进行中重复）+ 并行额度（maxConcurrent/availableSlots）；远程暴露时需 pair token [含 E2EE 头] 或 WebUI session
- `GET /mobile/spawn-options` — 远程新建任务可选 agents/projects（pair token 需 mobile_hub_list purpose）
- `POST /mobile/spawn` — 远程创建会话（选择 agent/project + 初始消息 → 创建 chat → 签发 scoped token → 返回 mobilePath）
- `GET /mobile/takeover/{chatId}/snapshot` — takeover 实时预览截图（pair token 需 chat 绑定一致；支持 E2EE 响应）
- `POST /node/events` — 接收已配对移动节点或外部自动化上报的系统事件（pair token `mobile_hub_list` 范围或 WebUI session 鉴权），交给 Cron 调度器的 `dispatch_system_event` 匹配活跃的系统事件触发器，返回触发数

## 模块依赖

- `app.remote_access.tunnel_manager` — CF quick tunnel
- `app.remote_access.tailscale_service` — Tailscale 守护进程状态探测
- `app.remote_access.pairing` — Pairing token
- `app.remote_access.e2ee` — E2EE 握手与会话（子包见 `e2ee/_ARCH.md`）
- `app.remote_access.mobile_gate` — 远程路径鉴权（含 spawn-options/spawn 路径白名单与统一门禁 `require_remote_access_gate`）
- `app.remote_access.mobile_hub_payload` — Hub sessions 响应组装（agentName 注入 + recentSessions）
- `app.services.agent.gateway` — 活跃会话列表
- `app.services.agent.agent_service` — Agent 列表（spawn-options / sessions agentName）
- `app.services.project.project_service` — Project 列表与 move_chat（spawn-options/spawn）
- `app.services.chat.chat_service` — Chat 存在性检查（pairing upgrade）与列表（recentSessions）、Chat 创建（spawn）
- `app.services.agent.browser_snapshot` — 浏览器截图与页面元信息聚合
- `app.core.cron.adapters.setup` — `get_cron_scheduler`（节点事件分发）
