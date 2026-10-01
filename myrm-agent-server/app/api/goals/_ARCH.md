# api/goals/

## 架构概述

长时 Goal 编排 HTTP 层。提供单会话 Goal 操作（暂停/恢复/取消/预算/subgoal/约束/DAG/队列）和全局跨会话 Goal 聚合接口。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Goal API exports. | [Pass] |
| `router.py` | 主路由 | Goal HTTP 聚合端点：`GET /goals/active`、状态与生命周期操作、子路由挂载 | [Pass] |
| `plan.py` | 路由与重演 | `GET /{session_id}/plan` 与 `GET /{session_id}/dag`，会话分支状态重演与工作区回退 | [Pass] |
| `queue.py` | 路由 | Goal 队列管理（查询、取消、重排）端点 | [Pass] |
| `constraints.py` | 路由 | Goal 约束管理与目标动态热编辑端点 | [Pass] |

## 关键常量

- `_NON_TERMINAL_STATUSES`: 6 种非终态状态的 frozenset，被 statistics/router.py 复用
