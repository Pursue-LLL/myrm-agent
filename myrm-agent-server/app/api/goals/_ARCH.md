# api/goals/

## 架构概述

长时 Goal 编排 HTTP 层。提供单会话 Goal 操作（暂停/恢复/取消/预算/subgoal/约束/DAG/队列）和全局跨会话 Goal 聚合接口。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Goal API exports. | ✅ |
| `router.py` | 路由 | Goal HTTP 端点：`GET /goals/active`（全局活跃 Goal 聚合）、`GET/POST /{session_id}/status`（状态查询与更新）、subgoals、constraints、objective、budget、plan、DAG、queue 管理 | ✅ |

## 关键常量

- `_NON_TERMINAL_STATUSES`: 6 种非终态状态的 frozenset，被 statistics/router.py 复用
