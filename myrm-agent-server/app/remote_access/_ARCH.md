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
| `trust_zone.py` | 核心 | AdmissionPath / TrustZone 解析；`resolve_request_local_trusted` | ✅ |
| `tool_policy.py` | 核心 | 远程暴露时 harness `SecurityConfig.remote_exposed()` deny overlay | ✅ |
| `pairing.py` | 核心 | 移动端 deep link 签名 token（24h TTL） | ✅ |
| `tunnel_manager.py` | 核心 | cloudflared quick tunnel 子进程 + 5s watchdog + shutdown hook | ✅ |

---

## API 入口

`app/api/remote_access/router.py` — `/api/v1/remote-access/*`

- `GET /mobile/sessions`：`trust_zone=remote_exposed` 时 **必须** 有效 `pair` token
- `POST /pairing-token`：签发 Hub deep link
- `GET|POST /tunnel/*`：CF quick tunnel 控制

---

## 依赖关系

- `app/core/security/auth/identity.py` — 消费 trust_zone 决定 local bypass
- `app/middleware/auth.py` — 注入 `request.state.admission_path` / `trust_zone` / `local_trusted`
- `app/middleware/session_idle.py` — 远程 30min sliding session
- `app/middleware/host_allowlist.py` — ingress + tunnel hostname + loopback/LAN Host 校验
- `app/services/webui/auth_service.py` — WebUI 状态解析使用 `resolve_request_local_trusted`
- `app/services/agent/params/converter.py` — 远程 Tool 策略 overlay
- `myrm_agent_harness.agent.security.config.remote_exposed_permissions` — deny key SSOT

---

## 被依赖方

- `app/api/remote_access/router.py`
- `app/server/lifespan.py` — shutdown 时 `tunnel_manager.shutdown()`
- `tests/remote_access/` — trust_zone / tool_policy / pairing / host_allowlist / mobile_sessions
