# api/remote_access/ 模块架构

## 架构概述

远程访问 HTTP 入口：CF quick tunnel 启停、E2EE 握手、移动端 Pairing Token 签发、Mobile Hub 会话查询。业务与安全逻辑见 [app/remote_access/_ARCH.md](../../remote_access/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `router.py` | 路由 | `/api/v1/remote-access/*` REST 端点 | ✅ |

## 端点

- `GET|POST /tunnel/*` — tunnel 状态与生命周期
- `GET /e2ee/public-key` — daemon 公钥（QR URL fragment `#e2ee=`）
- `POST /e2ee/handshake` — `e2ee_hello` → `e2ee_ready` + sessionId（30/min 限流）
- `POST /pairing-token` — WebUI session 签发 Hub list token；list pair upgrade **活跃** scoped token；支持 `browser_takeover` purpose 并返回 `mobilePath/mobileUrl`
- `POST /pairing-token/refresh` — pair token 续期（Hub list / scoped 控制 / browser takeover），返回续期后的 `mobilePath/mobileUrl`
- `GET /mobile/sessions` — 活跃 Agent 会话（远程暴露时需 pair token [含 E2EE 头] 或 WebUI session）
- `GET /mobile/spawn-options` — 远程新建任务可选 agents/projects（pair token 需 mobile_hub_list purpose）
- `POST /mobile/spawn` — 远程创建会话（选择 agent/project + 初始消息 → 创建 chat → 签发 scoped token → 返回 mobilePath；30/min 限流）
- `GET /mobile/takeover/{chatId}/snapshot` — takeover 实时预览截图（pair token 需 chat 绑定一致；支持 E2EE 响应）

## 模块依赖

- `app.remote_access.tunnel_manager` — CF quick tunnel
- `app.remote_access.pairing` — Pairing token
- `app.remote_access.e2ee` — E2EE 握手与会话（子包见 `e2ee/_ARCH.md`）
- `app.remote_access.mobile_gate` — 远程路径鉴权（含 spawn-options/spawn 路径白名单）
- `app.services.agent.gateway` — 活跃会话列表
- `app.services.agent.agent_service` — Agent 列表（spawn-options）
- `app.services.project.project_service` — Project 列表与 move_chat（spawn-options/spawn）
- `app.services.chat.chat_crud` — Chat 创建（spawn）
- `app.services.agent.browser_snapshot` — 浏览器截图与页面元信息聚合
