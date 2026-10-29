# activity-feed/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ActivityFeedAggregatorDeck.tsx` | 组件 | Implementation for Item 190 main deck. Collects heterogeneous events across 6 source systems and orchestrates auto-evaporating queues. | ✅ |
| `ActivityFeedStreamCard.tsx` | 组件 | Implementation for Item 190 individual feed item card. Handles autonomous resolution fade-out cues, executive bottlenecks, and one-click approvals. | ✅ |
| `activityFeedEngine.ts` | 引擎 | Pure computation and classification engine for Item 190. Implements two-phase autonomous categorization, priority pinning, and evaporation progress calculations. | ✅ |
| `activityFeedTypes.ts` | 类型 | Unified contract for Item 190: ActivityFeedMultiSystemAggregatorAndAutoEvaporatingQueueSuite. Aggregates multi-source events (Email, Calendar, Messaging, Approvals, Cron, Kanban) and governs two-phase autonomous evaporation vs pinned executive decision bottlenecks. | ✅ |
| `index.ts` | 入口 | Public entrypoint for activity feed types, engine, store, card, and aggregator deck. | ✅ |
| `useActivityFeedStore.ts` | 状态仓库 | Central reactive dispatcher for Item 190. Governs live ingestion from email, calendar, messaging, approvals, cron, and kanban, managing smooth automatic evaporation and undoable archives. | ✅ |
| `__tests__/ActivityFeedAggregatorDeck.test.tsx` | 测试 | `ActivityFeedAggregatorDeck`；7 个用例 | — |
| `__tests__/ActivityFeedStreamCard.test.tsx` | 测试 | `ActivityFeedStreamCard`；3 个用例 | — |
| `__tests__/activityFeedEngine.test.ts` | 测试 | `activityFeedEngine`；12 个用例 | — |
| `__tests__/activityFeedTypes.test.ts` | 测试 | `activityFeedTypes`；4 个用例 | — |
| `__tests__/useActivityFeedStore.test.ts` | 测试 | `useActivityFeedStore`；8 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
