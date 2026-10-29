# approval/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ExecutiveApprovalCard.tsx` | 组件 | 导出 `ExecutiveApprovalCard`；类型 `ExecutiveApprovalCardProps` | — |
| `VisualGatekeepingDeck.tsx` | 组件 | 导出 `VisualGatekeepingDeck`；类型 `VisualGatekeepingDeckProps` | — |
| `executiveApprovalEngine.ts` | 引擎 | 导出 `evaluateRiskLevel`、`computeApprovalStats`、`applyApprovalDecision`、`DEFAULT_APPROVAL_REQUESTS` | — |
| `executiveApprovalTypes.ts` | 类型 | 导出类型 `ApprovalRiskLevel`、`ApprovalActionType`、`ApprovalStatus`、`ApprovalRequest`、`ApprovalDecision`、`ApprovalStats` | — |
| `index.ts` | 入口 | 聚合导出 `./executiveApprovalTypes`、`./executiveApprovalEngine`、`./useExecutiveApprovalStore`、`./ExecutiveApprovalCard`、`./VisualGatekeepingDeck` | — |
| `useExecutiveApprovalStore.ts` | 状态仓库 | 导出 `useExecutiveApprovalStore`；类型 `ExecutiveApprovalState` | — |
| `__tests__/ExecutiveApprovalCard.test.tsx` | 测试 | `ExecutiveApprovalCard`；5 个用例 | — |
| `__tests__/VisualGatekeepingDeck.test.tsx` | 测试 | `VisualGatekeepingDeck`；4 个用例 | — |
| `__tests__/executiveApprovalEngine.test.ts` | 测试 | `executiveApprovalEngine`；8 个用例 | — |
| `__tests__/useExecutiveApprovalStore.test.ts` | 测试 | `useExecutiveApprovalStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
