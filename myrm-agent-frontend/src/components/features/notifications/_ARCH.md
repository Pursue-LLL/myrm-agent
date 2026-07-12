# notifications/

## 架构概述

应用内通知与 toast 聚合展示组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `NotificationBell.tsx` | 核心 | NavBar 通知铃铛：未读计数、Popover 列表与已读标记 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
