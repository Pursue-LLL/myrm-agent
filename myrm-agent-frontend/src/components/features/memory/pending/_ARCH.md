# memory/pending/

## 架构概述

待审批记忆：新增记忆在落库前进入审批队列，本目录提供计数徽标、审批弹窗与批量列表。

## 文件清单

| 文件                      | 地位 | 职责                              | I/O/P |
| ------------------------- | ---- | --------------------------------- | ----- |
| `PendingMemoryBadge.tsx`  | 核心 | 待审批计数徽标（入口提示）        | ✅    |
| `PendingMemoryDialog.tsx` | 核心 | 单条待审批记忆的接受/拒绝弹窗     | ✅    |
| `PendingMemoryList.tsx`   | 核心 | 待审批批量列表与批量接受/拒绝     | ✅    |

## 依赖

- `@/store/*`、`@/services/memory`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
