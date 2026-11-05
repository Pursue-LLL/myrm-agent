# channels/routing/commands/router_commands/

## 架构概述

Router 命令 mixin 域：`mixin.py` 把各命令族 mixin 组合成 `RouterCommandsMixin`，各命令族一个模块。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合门面，导出全部 mixin 与 `DraftAction` |
| `mixin.py` | 组合基类 `RouterCommandsMixin` |
| `approval.py` / `approval_end.py` | 审批命令与审批超时/被取代收尾 |
| `delegation.py` | `/delegate` 委派与审批交接 |
| `draft.py` | `/draft` 决定与 `DraftAction` |
| `goals.py` | `/goal`、`/subgoal`、`/background`、`/handoff` |
| `memory.py` | `/status`、`/kanban`、`/learn`、`/memory` |
| `modes.py` | `/yolo`、`/personality`、`/steer`、`/queue` |
| `quota.py` | `/quota` |
| `session.py` | `/new`、`/compact`、`/retry`、`/undo`、话题命令 |
| `stop.py` | `/stop` 与会话中止 |
