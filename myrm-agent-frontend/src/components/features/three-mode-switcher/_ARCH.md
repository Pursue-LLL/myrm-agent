# three-mode-switcher/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ThreeModeCapsuleSwitcher.tsx` | 组件 | 导出 `ThreeModeCapsuleSwitcher` | — |
| `ThreeModeIntentGuidanceToast.tsx` | 组件 | 导出 `ThreeModeIntentGuidanceToast` | — |
| `ThreeModePermissionMatrixDeck.tsx` | 组件 | 导出 `ThreeModePermissionMatrixDeck` | — |
| `index.ts` | 入口 | 聚合导出 `./threeModeTypes`、`./threeModeEngine`、`./useThreeModeStore`、`./ThreeModeCapsuleSwitcher`、`./ThreeModeIntentGuidanceToast`、`./ThreeModePermissionMatrixDeck` | — |
| `threeModeEngine.ts` | 引擎 | 导出 `OFFICE_MODES`、`resolveModeSecurityPolicy`、`detectWriteIntentInAskMode` | — |
| `threeModeTypes.ts` | 类型 | 导出类型 `OfficeWorkspaceMode`、`ModeSecurityPolicy`、`OfficeModeMetadata`、`WriteIntentDetectionResult` | — |
| `useThreeModeStore.ts` | 状态仓库 | 导出 `useThreeModeStore` | — |
| `__tests__/ThreeModeCapsuleSwitcher.test.tsx` | 测试 | `ThreeModeCapsuleSwitcher 组件单测`；4 个用例 | — |
| `__tests__/ThreeModeIntentGuidanceToast.test.tsx` | 测试 | `ThreeModeIntentGuidanceToast 组件单测`；4 个用例 | — |
| `__tests__/ThreeModePermissionMatrixDeck.test.tsx` | 测试 | `ThreeModePermissionMatrixDeck 组件单测`；4 个用例 | — |
| `__tests__/threeModeEngine.test.ts` | 测试 | `threeModeEngine 核心逻辑单测`；4 个用例 | — |
| `__tests__/useThreeModeStore.test.ts` | 测试 | `useThreeModeStore 状态单测`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
