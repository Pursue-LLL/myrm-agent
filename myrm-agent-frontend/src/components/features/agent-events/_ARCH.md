# agent-events/

## 架构概述

Agent 运行期事件展示与调试面板（流式状态、步骤可视化）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `EventTimeline.tsx` | 核心 | Agent 运行事件时间线（步骤/工具/状态变更可视化） | ✅ |
| `PermissionDialog.tsx` | 辅助 | Agent 事件调试面板内的权限确认弹窗 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
