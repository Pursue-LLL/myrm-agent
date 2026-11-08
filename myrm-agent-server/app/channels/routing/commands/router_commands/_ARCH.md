# channels/routing/commands/router_commands/

## 架构概述

Router 命令 mixin 域：`mixin.py` 把各命令族 mixin 组合成 `RouterCommandsMixin`，各命令族一个模块。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合门面，导出全部 mixin 与 `DraftAction` | ✅ |
| `mixin.py` | 核心 | 组合基类 `RouterCommandsMixin` | ✅ |
| `approval.py` / `approval_end.py` | 核心 | 审批命令与审批超时/被取代收尾 | ✅ |
| `delegation.py` | 核心 | `/delegate` 委派与审批交接 | ✅ |
| `draft.py` | 核心 | `/draft` 决定与 `DraftAction` | ✅ |
| `goals.py` | 核心 | `/goal`、`/subgoal`、`/background`、`/handoff` | ✅ |
| `memory.py` | 核心 | `/status`、`/kanban`、`/learn`、`/memory` | ✅ |
| `modes.py` | 核心 | `/yolo`、`/personality`、`/steer`、`/queue` | ✅ |
| `quota.py` | 核心 | `/quota` | ✅ |
| `session.py` | 核心 | `/new`、`/compact`、`/retry`、`/undo`、话题命令 | ✅ |
| `stop.py` | 核心 | `/stop` 与会话中止 | ✅ |

## 依赖关系

- `mixin.py` → `approval.py`
- `mixin.py` → `approval_end.py`
- `mixin.py` → `delegation.py`
- `mixin.py` → `draft.py`
- `mixin.py` → `goals.py`
- `mixin.py` → `memory.py`
- `mixin.py` → `modes.py`
- `mixin.py` → `quota.py`
- `mixin.py` → `session.py`
- `mixin.py` → `stop.py`
