# remote_access 模块架构

---

## 架构概述

远程访问安全与穿透：按 **Admission Path** 标记请求信任域（非 IP），驱动会话 idle 超时、
外网 Tool 策略与 Host allowlist。提供 CF quick tunnel 生命周期（含 watchdog）、PairingToken
与 Mobile Hub API。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `trust_zone.py` | 核心 | AdmissionPath / TrustZone 解析 | ✅ |
| `mobile_gate.py` | 核心 | scoped pair token 校验；`resolve_request_pair_token`（E2EE/query/header）；HTTP + `/ws/stt/*` mobile 控制面路径 | ✅ |
| `mobile_deep_link.py` | 核心 | Channel → 前端 deep link 构建：`/mobile/status` (HITL) + `/{chatId}` (WebUI 续聊) | ✅ |
| `tool_policy.py` | 核心 | 远程暴露时 harness `SecurityConfig.remote_exposed()` deny overlay | ✅ |
| `pairing.py` | 核心 | HMAC 签名 token；`mobile_hub_list`（Hub 列表）、`mobile_hub`（scoped 控制）、`browser_takeover`（takeover 最小权限）；改密时 `rotate_pairing_key` | ✅ |
| `e2ee/` | 子包 | Mobile remote E2EE：crypto / keystore / session / response / sse（见 `e2ee/_ARCH.md`） | ✅ |
| `tunnel_manager.py` | 核心 | cloudflared quick tunnel 子进程 + 5s watchdog + shutdown hook | ✅ |

---

## API 入口

`app/api/remote_access/router.py` — `/api/v1/remote-access/*`

- `GET /mobile/sessions`：`trust_zone=remote_exposed` 时需有效 `mobile_hub_list` pair（query / header / E2EE 解密）或 WebUI session
- `POST /pairing-token`：WebUI session 签发 Hub QR / takeover deep link；`mobile_hub_list` pair 仅可 upgrade **活跃** 会话 scoped token；`browser_takeover` token 定向 `/mobile/takeover/{chatId}` 并最小权限放行 agent-stream + refresh
- scoped control token 经 `request.state.pair_bound_chat_id` 绑定 attach/steer/agent-stream/**chat cancel**（不含 `/agents/agent/{message_id}/cancel`）
- `POST /agents/chats/{chat_id}/cancel`（`general_agent/streaming.py`）：Mobile Stop → `gateway.interrupt_session` + `CancellationRegistry.cancel`（`ActiveSessionInfo.current_message_id`）
- `POST /pairing-token/refresh`：`mobile_hub_list` / scoped pair 续期
- `POST /node/events`：外部节点（移动设备/IoT/Shortcuts/Tasker）上报系统事件；`mobile_hub_list` pair 或 WebUI session 鉴权；内部路由至 `CronScheduler.dispatch_system_event`（60/min 限流）
- `GET|POST /tunnel/*`：CF quick tunnel 控制
- `GET /e2ee/public-key`：daemon 公钥（QR fragment `#e2ee=`）
- `POST /e2ee/handshake`：`e2ee_hello` → `e2ee_ready` + sessionId（30/min 限流）

---

## 中间件集成

- `app/middleware/auth.py` — 解析 admission_path / trust_zone，pair token bypass
- `app/middleware/e2ee.py` — mobile remote E2EE 请求解密；活跃 E2EE 请求 sliding refresh session TTL
- `app/middleware/host_allowlist.py` — DNS rebinding 防护
- `app/middleware/session_idle.py` — 远程 30min sliding WebUI session
- `app/core/security/auth/identity.py` — identity SSOT（含 pair_token auth_source）

---

## 依赖关系

- `app/services/agent/params/converter.py` — 消费 trust_zone 叠加 remote tool deny
- `app/channels/routing/router_stream.py` — HITL 审批 outbound mobile deep link 按钮
- `app/channels/routing/router_execution.py` — IM 回复附加 WebUI 续聊 deep link 按钮
- `app/core/channel_bridge/btw_notifier.py` — BTW 完成通知附加 WebUI 续聊 deep link 按钮
- `myrm_agent_harness.agent.security.config.remote_exposed_permissions` — deny key SSOT

---

## 被依赖方

- `app/api/remote_access/router.py`
- `app/server/lifespan.py` — shutdown 时 `tunnel_manager.shutdown()`
- `tests/remote_access/` — trust_zone / pairing / mobile_gate / auth / sessions / pairing upgrade
