# workspace/scaffolding/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个状态仓库、1 个引擎、1 个类型），4 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ScaffoldingDocPreviewModal.tsx` | 组件 | 导出 `ScaffoldingDocPreviewModal` | — |
| `WorkspaceScaffoldingCard.tsx` | 组件 | 导出 `WorkspaceScaffoldingCard` | — |
| `index.ts` | 入口 | 聚合导出 `./workspaceScaffoldingTypes`、`./workspaceScaffoldingEngine`、`./useWorkspaceScaffoldingStore`、`./WorkspaceScaffoldingCard`、`./ScaffoldingDocPreviewModal` | — |
| `useWorkspaceScaffoldingStore.ts` | 状态仓库 | 导出 `useWorkspaceScaffoldingStore` | — |
| `workspaceScaffoldingEngine.ts` | 引擎 | 导出 `parseScaffoldingIntent`、`inferFileZoneClassification`、`generateDefaultScaffoldingProposal`、`summarizeScaffoldingProposal` | — |
| `workspaceScaffoldingTypes.ts` | 类型 | 导出类型 `FourZoneCategory`、`ProposedFileMove`、`GeneratedScaffoldDoc`、`ScaffoldingStatus`、`ScaffoldingProposal` | — |
| `__tests__/ScaffoldingDocPreviewModal.test.tsx` | 测试 | `ScaffoldingDocPreviewModal`；5 个用例 | — |
| `__tests__/WorkspaceScaffoldingCard.test.tsx` | 测试 | `WorkspaceScaffoldingCard`；7 个用例 | — |
| `__tests__/useWorkspaceScaffoldingStore.test.ts` | 测试 | `useWorkspaceScaffoldingStore`；6 个用例 | — |
| `__tests__/workspaceScaffoldingEngine.test.ts` | 测试 | `workspaceScaffoldingEngine`；8 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
