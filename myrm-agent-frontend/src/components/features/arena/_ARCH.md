# arena/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AdoptSynthesizeBar.tsx` | 组件 | 导出 `AdoptSynthesizeBar`；类型 `AdoptSynthesizeBarProps` | — |
| `LocalProjectWorkspaceCard.tsx` | 组件 | 导出 `LocalProjectWorkspaceCard`；类型 `LocalProjectWorkspaceCardProps` | — |
| `MultiModelSplitArenaView.tsx` | 组件 | 导出 `MultiModelSplitArenaView`；类型 `MultiModelSplitArenaViewProps` | — |
| `arenaEngine.ts` | 引擎 | 导出 `DEFAULT_ARENA_MODELS`、`createInitialStreamState`、`buildSynthesizePrompt`、`validateLocalProjectPath`、`calculateDiffSimilarity` | — |
| `arenaTypes.ts` | 类型 | 导出类型 `ArenaStreamStatus`、`ArenaLayoutMode`、`ArenaModelConfig`、`ArenaModelStream`、`ArenaAdoptDecision`、`LocalProjectBinding` | — |
| `index.ts` | 入口 | 聚合导出 `./arenaTypes`、`./arenaEngine`、`./useArenaStore`、`./MultiModelSplitArenaView`、`./AdoptSynthesizeBar`、`./LocalProjectWorkspaceCard` | — |
| `useArenaStore.ts` | 状态仓库 | 导出 `useArenaStore`；类型 `ArenaState` | — |
| `__tests__/AdoptSynthesizeBar.test.tsx` | 测试 | `AdoptSynthesizeBar`；3 个用例 | — |
| `__tests__/LocalProjectWorkspaceCard.test.tsx` | 测试 | `LocalProjectWorkspaceCard`；4 个用例 | — |
| `__tests__/MultiModelSplitArenaView.test.tsx` | 测试 | `MultiModelSplitArenaView`；4 个用例 | — |
| `__tests__/arenaEngine.test.ts` | 测试 | `arenaEngine`；8 个用例 | — |
| `__tests__/useArenaStore.test.ts` | 测试 | `useArenaStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
