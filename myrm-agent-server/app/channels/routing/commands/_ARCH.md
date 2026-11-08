# channels/routing/commands/

## 架构概述

IM 渠道斜杠命令解析与执行域：统一命令解析入口与各功能域命令实现（审批、停止、目标、记忆与配额状态诊断、模式交互）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出，保持 `router_commands` import 稳定 | [OK] |
| `parsers.py` | 模块 | 斜杠命令参数解析（approval / yolo / personality / memory），纯函数 | [OK] |
| `session.py` | 模块 | `/new` 与 `/compact` 会话级处理 | [OK] |
| `topic.py` | 模块 | 话题命令解析与绑定/解绑/切换处理 | [OK] |
| `turns.py` | 模块 | `/retry`、`/undo` 与文件回退提示 | [OK] |
| `router_commands/` | 子包 | `mixin.py` 组合九个命令族 mixin（approval/approval_end/delegation/draft/goals/memory/modes/quota/session/stop），`__init__.py` 为聚合门面；详见 [router_commands/_ARCH.md](router_commands/_ARCH.md) | [OK] |

## 依赖关系

- 各模块无横向依赖，全部通过 `__init__.py` 聚合。
