# channels/routing/commands/

## 架构概述

IM 渠道斜杠命令解析与执行域：统一命令解析入口与各功能域命令实现（审批、目标、记忆与配额状态诊断、模式交互）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出，保持 `router_commands` import 稳定 | [OK] |
| `commands.py` | 模块 | 命令解析与斜杠命令执行统一入口 | [OK] |
| `router_commands.py` | 模块 | 基础命令路由与调度 | [OK] |
| `router_commands_approval.py` | 模块 | 审批相关命令（approve/reject 等） | [OK] |
| `router_commands_goals.py` | 模块 | 目标（goal）相关命令 | [OK] |
| `router_commands_memory.py` | 模块 | 会话状态诊断（/status）、看板与长期记忆交互（/kanban, /learn, /memory） | [OK] |
| `router_commands_modes.py` | 模块 | 模式切换命令 | [OK] |
| `router_commands_quota.py` | 模块 | 配额使用诊断与本地直出（/quota）、字符进度条与动态倒计时 | [OK] |
