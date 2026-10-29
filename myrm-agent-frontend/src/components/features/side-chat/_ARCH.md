# side-chat/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `SideChatDrawer.tsx` | 组件 | 导出 `SideChatDrawer`；类型 `SideChatDrawerProps` | — |
| `SideChatTriggerButton.tsx` | 组件 | 导出 `SideChatTriggerButton`；类型 `SideChatTriggerButtonProps` | — |
| `index.ts` | 入口 | 聚合导出 `./sideChatTypes`、`./sideChatEngine`、`./useSideChatStore`、`./SideChatDrawer`、`./SideChatTriggerButton` | — |
| `sideChatEngine.ts` | 引擎 | 导出 `classifySideChatIntent`、`generateInstantCollaboratorReply`、`createSteeringItemFromMessage`、`formatSteeringQueueForMainAgent` | — |
| `sideChatTypes.ts` | 类型 | 导出类型 `SteeringIntentType`、`SteeringStatus`、`SideChatMessage`、`SteeringBufferItem`、`MainTaskProgressInfo`、`SideChatState` | — |
| `useSideChatStore.ts` | 状态仓库 | 导出 `useSideChatStore`；类型 `SideChatActions`、`SideChatStore` | — |
| `__tests__/SideChatDrawer.test.tsx` | 测试 | `SideChatDrawer`；6 个用例 | — |
| `__tests__/SideChatTriggerButton.test.tsx` | 测试 | `SideChatTriggerButton`；3 个用例 | — |
| `__tests__/sideChatEngine.test.ts` | 测试 | `sideChatEngine`；4 个用例 | — |
| `__tests__/sideChatIntegration.test.ts` | 测试 | `sideChatIntegration`；1 个用例 | — |
| `__tests__/useSideChatStore.test.ts` | 测试 | `useSideChatStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
