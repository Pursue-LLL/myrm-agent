# chat-window/ambient-activity/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AmbientActivityDeck.tsx` | 组件 | 导出 `AmbientActivityDeck` | — |
| `BotCommunicationInspectionDrawer.tsx` | 组件 | 导出 `BotCommunicationInspectionDrawer` | — |
| `ambientActivityEngine.ts` | 引擎 | 导出 `filterVisibleConversations`、`aggregateAmbientActivities`、`formatMicroActivitySummary` | — |
| `ambientActivityTypes.ts` | 类型 | 导出类型 `VisibilityScope`、`BotActivityStatus`、`BotActivityItem`、`AmbientDeckSummary`、`ConversationWithVisibility` | — |
| `index.ts` | 入口 | 聚合导出 `./ambientActivityTypes`、`./ambientActivityEngine`、`./useAmbientActivityStore`、`./AmbientActivityDeck`、`./BotCommunicationInspectionDrawer` | — |
| `useAmbientActivityStore.ts` | 状态仓库 | 导出 `useAmbientActivityStore` | — |
| `__tests__/AmbientActivityDeck.test.tsx` | 测试 | `AmbientActivityDeck`；5 个用例 | — |
| `__tests__/BotCommunicationInspectionDrawer.test.tsx` | 测试 | `BotCommunicationInspectionDrawer`；6 个用例 | — |
| `__tests__/ambientActivityEngine.test.ts` | 测试 | `ambientActivityEngine`；6 个用例 | — |
| `__tests__/useAmbientActivityStore.test.ts` | 测试 | `useAmbientActivityStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
