# desktop-pet-pulse/

## 架构概述

8 个源文件（4 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `DataMigrationCenterModal.tsx` | 组件 | 导出 `DataMigrationCenterModal`；类型 `DataMigrationCenterModalProps` | — |
| `FloatingPetBall.tsx` | 组件 | 导出 `FloatingPetBall`；类型 `FloatingPetBallProps` | — |
| `PetControlQuickActionDrawer.tsx` | 组件 | 导出 `PetControlQuickActionDrawer`；类型 `PetControlQuickActionDrawerProps` | — |
| `VoiceDirectInputBubble.tsx` | 组件 | 导出 `VoiceDirectInputBubble`；类型 `VoiceDirectInputBubbleProps` | — |
| `desktopPetPulseEngine.ts` | 引擎 | 导出 `derivePetVisualConfig`、`computeStackedAgentBadges`、`formatVoiceDispatchPayload`、`validateMigrationBundle`、`executeDataMigrationMerge` | — |
| `desktopPetPulseTypes.ts` | 类型 | 导出类型 `PetPulseStatus`、`PetExpression`、`AgentIdentityProjection`、`SecondaryAgentBadge`、`PetPulseVisualConfig`、`VoiceDirectInputState` 等 19 个 | — |
| `index.ts` | 入口 | 聚合导出 `./desktopPetPulseTypes`、`./desktopPetPulseEngine`、`./useDesktopPetPulseStore`、`./FloatingPetBall`、`./VoiceDirectInputBubble`、`./PetControlQuickActionDrawer`、`./DataMigrationCenterModal` | — |
| `useDesktopPetPulseStore.ts` | 状态仓库 | 导出 `useDesktopPetPulseStore`；类型 `DesktopPetPulseStoreState` | — |
| `__tests__/DataMigrationCenterModal.test.tsx` | 测试 | `DataMigrationCenterModal`；5 个用例 | — |
| `__tests__/FloatingPetBall.test.tsx` | 测试 | `FloatingPetBall`；6 个用例 | — |
| `__tests__/VoiceDirectInputBubble.test.tsx` | 测试 | `VoiceDirectInputBubble`；4 个用例 | — |
| `__tests__/desktopPetPulseEngine.test.ts` | 测试 | `desktopPetPulseEngine`；5 个用例 | — |
| `__tests__/useDesktopPetPulseStore.test.ts` | 测试 | `useDesktopPetPulseStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
