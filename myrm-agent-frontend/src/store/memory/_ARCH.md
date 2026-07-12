# store/memory/ 模块架构

## 架构概述

记忆中心 UI 状态：列表分页、待确认记忆、统计与冲突解决草稿。HTTP 调用在 `@/services/memory*`；本目录仅 Zustand。

## 文件清单

| 文件 | 职责 |
|------|------|
| `useMemoryStore.ts` | 记忆列表、筛选、CRUD 乐观更新 |
| `types.ts` | `Memory`、`PendingMemory`、`MemoryStatsResponse` 等 |
| `index.ts` | 类型与 store 再导出（子模块唯一允许的桶入口） |

## 依赖

- `@/services/memory.ts`、`memoryArchive.ts` — REST
- `@/components/features/memory/*` — 消费方

## 约束

- 域类型放 `types.ts`；勿与 `src/types/` 重复定义
