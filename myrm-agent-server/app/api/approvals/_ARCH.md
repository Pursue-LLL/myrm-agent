# api/approvals/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Approval HTTP endpoints. | ✅ |
| `router.py` | 路由 | `GET /approvals` recovery 列表；`POST /{id}/resolve` 落库 + SSE（Web subagent 由前端先 agent-stream resume） | ✅ |

## API 契约

- `GET /api/v1/approvals`：仅返回需全局 Approval Drawer 的 pending 项（详见 `services/approvals/_ARCH.md`）。
- `POST /api/v1/approvals/{id}/resolve`：接受 `decision`、`comment`、`edited_payload`、`allow_always`（bool 或 `{tool,args}`）；`reject` 归一化为 `deny`；SSE `approval_resolved` 透传 `allow_always`。Web `subagent_approval` 须先经前端 `resumeDrawerApprovalStream` 再调本接口。
- Growth inbox 审阅走 `GET /api/v1/skills/drafts`，非本路由。
