# side-track/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `SideTrackExplainerDrawer.tsx` | 组件 | 导出 `SideTrackExplainerDrawer`；类型 `SideTrackExplainerDrawerProps` | — |
| `SideTrackForkTrigger.tsx` | 组件 | 导出 `SideTrackForkTrigger`；类型 `SideTrackForkTriggerProps` | — |
| `index.ts` | 入口 | 聚合导出 `./sideTrackTypes`、`./sideTrackEngine`、`./useSideTrackStore`、`./SideTrackExplainerDrawer`、`./SideTrackForkTrigger` | — |
| `sideTrackEngine.ts` | 引擎 | 导出 `generateForkedSnapshot`、`generatePresetInquiries`、`buildSideTrackSystemPrompt`、`createSideTrackSession`、`generateLocalExplainerAnswer` | — |
| `sideTrackTypes.ts` | 类型 | 导出类型 `ReadOnlyCodeSnapshot`、`ReadOnlyStepSnapshot`、`ForkedSessionSnapshot`、`SideTrackMessage`、`SideTrackSession` | — |
| `useSideTrackStore.ts` | 状态仓库 | 导出 `useSideTrackStore`；类型 `SideTrackStoreState` | — |
| `__tests__/SideTrackExplainerDrawer.test.tsx` | 测试 | `SideTrackExplainerDrawer`；6 个用例 | — |
| `__tests__/SideTrackForkTrigger.test.tsx` | 测试 | `SideTrackForkTrigger`；2 个用例 | — |
| `__tests__/sideTrackEngine.test.ts` | 测试 | `sideTrackEngine`；6 个用例 | — |
| `__tests__/sideTrackIntegration.test.tsx` | 测试 | `SideTrack Integration Suite`；1 个用例 | — |
| `__tests__/useSideTrackStore.test.ts` | 测试 | `useSideTrackStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
