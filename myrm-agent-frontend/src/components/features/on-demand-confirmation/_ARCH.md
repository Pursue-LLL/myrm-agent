# on-demand-confirmation/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `NineEntryNavigationShell.tsx` | 组件 | 导出 `NineEntryNavigationShell` | — |
| `OnDemandDecisionModal.tsx` | 组件 | 导出 `OnDemandDecisionModal` | — |
| `OnDemandOptionCard.tsx` | 组件 | 导出 `OnDemandOptionCard` | — |
| `index.ts` | 入口 | 聚合导出 `./onDemandConfirmationTypes`、`./onDemandConfirmationEngine`、`./useOnDemandConfirmationStore`、`./OnDemandOptionCard`、`./OnDemandDecisionModal`、`./NineEntryNavigationShell` | — |
| `onDemandConfirmationEngine.ts` | 引擎 | 导出 `mapKeyToOptionLetter`、`buildDecisionResult`、`NINE_ENTRY_NAV_ITEMS` | — |
| `onDemandConfirmationTypes.ts` | 类型 | 导出类型 `OptionLetterId`、`ConfirmationOptionItem`、`OnDemandDecisionInterrupt`、`ConfirmationDecisionResult`、`NineEntryId`、`EntryCategory` 等 7 个 | — |
| `useOnDemandConfirmationStore.ts` | 状态仓库 | 导出 `useOnDemandConfirmationStore` | — |
| `__tests__/NineEntryNavigationShell.test.tsx` | 测试 | `NineEntryNavigationShell 组件单测`；2 个用例 | — |
| `__tests__/OnDemandDecisionModal.test.tsx` | 测试 | `OnDemandDecisionModal 组件单测`；5 个用例 | — |
| `__tests__/OnDemandOptionCard.test.tsx` | 测试 | `OnDemandOptionCard 组件单测`；3 个用例 | — |
| `__tests__/onDemandConfirmationEngine.test.ts` | 测试 | `onDemandConfirmationEngine 核心逻辑单测`；4 个用例 | — |
| `__tests__/useOnDemandConfirmationStore.test.ts` | 测试 | `useOnDemandConfirmationStore 状态单测`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
