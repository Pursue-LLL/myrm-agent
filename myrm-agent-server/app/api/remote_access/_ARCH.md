# api/remote_access/ 模块架构

## 架构概述

远程访问 HTTP 入口：CF quick tunnel 启停、移动端 Pairing Token 签发、Mobile Hub 会话查询。业务与安全逻辑见 [app/remote_access/_ARCH.md](../../remote_access/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `router.py` | 路由 | `/api/v1/remote-access/*` REST 端点 | ✅ |

## 端点

- `GET|POST /tunnel/*` — tunnel 状态与生命周期
- `POST /pairing-token` — WebUI session 签发 Hub list token；list pair upgrade **活跃** scoped token
- `POST /pairing-token/refresh` — pair token 续期（Hub list / scoped 控制）
- `GET /mobile/sessions` — 活跃 Agent 会话（远程暴露时需 pair token 或 WebUI session）

## 模块依赖

- `app.remote_access.tunnel_manager` — CF quick tunnel
- `app.remote_access.pairing` — Pairing token
- `app.remote_access.mobile_gate` — 远程路径鉴权
- `app.services.agent.gateway` — 活跃会话列表
