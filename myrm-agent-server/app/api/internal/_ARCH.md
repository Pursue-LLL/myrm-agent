# api/internal/

## 架构概述

Control Plane → 用户沙箱内 server 的内部 HTTP 端点（**不**经 `/api/v1` 前缀聚合）。Token 鉴权或 CP 专用头；仅 SaaS/企业场景由 CP 调用。

上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `agent_interrupt.py` | 路由 | `POST /api/agent/interrupt` — 中断当前 Agent 执行 | ✅ |
| `skills_killswitch.py` | 路由 | `POST /api/internal/skills/killswitch` — CP 远程禁用/启用预置 Skill（`X-Telemetry-Token`） | ✅ |

## 挂载

`app/main.py` 直接 `include_router`（非 `api/router.py`）：

- `internal_agent_interrupt_router` → prefix `/api`
- `internal_skills_killswitch_router` → 自带 prefix `/api/internal/skills`

## 边界

- 属于 **server 业务层**（单机实例内操作），不是 CP 仓库代码
- CP 通过 HTTP 调用沙箱内这些端点；server **不 import** control-plane
