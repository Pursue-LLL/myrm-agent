# api/approvals/ 模块架构

## 架构概述

统一拦截审批 HTTP 入口：列出需全局 Drawer recovery 的 pending 项，解析单条或批量决策并广播 `APPROVAL_RESOLVED` 事件恢复 Agent。注册表与过滤契约见 [services/approvals/_ARCH.md](../../services/approvals/_ARCH.md)；前端 resume 编排见 [myrm-agent-frontend/src/lib/approval/_ARCH.md](../../../../myrm-agent-frontend/src/lib/approval/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `router.py` | 路由 | `GET /approvals`、`POST /{id}/resolve`、`POST /batch-resolve` | ✅ |

## 路由（前缀 `/api/v1/approvals`）

| 方法 | 路径 | 职责 |
|------|------|------|
| GET | `` | 分页列出 pending（`limit` 1–100，`offset`）；排除无 `thread_id` 的后台 growth draft |
| POST | `/{approval_id}/resolve` | 单条决策：`decision`（`approve`/`deny`/`reject`→`deny`）、`edited_payload`、`comment`、`allow_always`（bool 或 `{tool,args}`）；有 `thread_id` 时发布 `APPROVAL_RESOLVED` |
| POST | `/batch-resolve` | 批量 `approval_ids` + `decision`；逐条 resolve 并对有 `thread_id` 项发事件 |

## 契约要点

- **全局 Drawer recovery**：仅 `ApprovalRegistry.list_pending` 过滤后的项；growth inbox 走 `GET /api/v1/skills/drafts`。
- **Web `subagent_approval`**：前端 `resumeDrawerApprovalStream` **先于**本接口 resolve，与主聊天 HITL 同机制。
- **IM 渠道**：审批回调由 `channels/routing` 下发 `Command(resume=...)`，不经本 REST 路径。

## 模块依赖

- `app.services.approvals.registry` — `ApprovalRegistry`
- `myrm_agent_harness.agent.types` — `Command`（渠道 resume 路径）
