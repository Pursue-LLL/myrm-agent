# sidebar/attention-hub/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AttentionHubBadge.tsx` | 组件 | Implementation for Item 189 sidebar entry point. Shows live blocking count and alerts users when high-priority approvals or tasks require intervention. | ✅ |
| `AttentionHubPanel.tsx` | 组件 | Implementation for Item 189 attention hub drawer. Displays blocking tasks across concurrent sessions and provides one-click focus shuttle navigation. | ✅ |
| `attentionHubEngine.ts` | 引擎 | Pure computation and DOM navigation helper for Item 189: AttentionHubNotificationQueueAndInterventionBadgeSuite. Deterministically sorts multi-task attention items, calculates countdowns, and executes high-precision focus shuttle jumps to target message/approval nodes. | ✅ |
| `attentionHubTypes.ts` | 类型 | Unified contract for Item 189: AttentionHubNotificationQueueAndInterventionBadgeSuite. Consolidates blocking approvals, clarification cards, failed tasks, and milestone completions into an authoritative multi-task attention hub with priority grading and focus shuttle targets. | ✅ |
| `index.ts` | 入口 | Public entrypoint for attention hub types, engine, store, badge, and panel. | ✅ |
| `useAttentionHubStore.ts` | 状态仓库 | Central reactive dispatcher for Item 189. Manages live cross-session attention alerts, handles batch clears for resolved tasks, and orchestrates smooth focus shuttles. | ✅ |
| `__tests__/AttentionHubBadge.test.tsx` | 测试 | `AttentionHubBadge`；5 个用例 | — |
| `__tests__/AttentionHubPanel.test.tsx` | 测试 | `AttentionHubPanel`；8 个用例 | — |
| `__tests__/attentionHubEngine.test.ts` | 测试 | `attentionHubEngine`；15 个用例 | — |
| `__tests__/attentionHubTypes.test.ts` | 测试 | `attentionHubTypes`；4 个用例 | — |
| `__tests__/useAttentionHubStore.test.ts` | 测试 | `useAttentionHubStore`；8 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
