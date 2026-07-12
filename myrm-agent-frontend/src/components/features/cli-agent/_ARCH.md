# cli-agent/

## 架构概述

CLI Agent 配置与状态展示（外部 Agent 桥接）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AgentSelector.tsx` | 核心 | 外部 CLI Agent 选择与切换下拉 | ✅ |
| `PermissionDialog.tsx` | 核心 | CLI Agent 权限请求确认对话框 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
