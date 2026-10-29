# chat-window/rules-hot-reload/

## 架构概述

5 个源文件（1 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `WorkspaceRulesIndicatorBar.tsx` | 组件 | Visual status bar for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite. Renders active AGENTS.md / CLAUDE.md status, content hashes, manual /reload triggers, real-time update notifications, and the global rules bypass toggle (--no-context-files). | ✅ |
| `index.ts` | 入口 | Public API entry point for workspace rules hot-reload, file watcher engine, and indicator bar. | ✅ |
| `rulesHotReloadEngine.ts` | 引擎 | Pure computation engine for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite. Calculates content hashes, validates rule file identifiers, computes structural diffs, formats status toasts, and broadcasts zero-restart cache invalidation events. | ✅ |
| `rulesHotReloadTypes.ts` | 类型 | Unified contracts for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite. Supports zero-restart AGENTS.md / CLAUDE.md file-watcher hot reload, real-time session invalidation event bus, and global rules bypass switch (--no-context-files). | ✅ |
| `useWorkspaceRulesStore.ts` | 状态仓库 | Central reactive dispatcher for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite. Manages active workspace rule files, automatic content-hash diffing, zero-restart cache invalidation, and the global rules bypass toggle (--no-context-files). | ✅ |
| `__tests__/WorkspaceRulesIndicatorBar.test.tsx` | 测试 | `WorkspaceRulesIndicatorBar Component`；5 个用例 | — |
| `__tests__/rulesHotReloadEngine.test.ts` | 测试 | `rulesHotReloadEngine`；11 个用例 | — |
| `__tests__/rulesHotReloadIntegration.test.tsx` | 测试 | `WorkspaceRules Hot-Reload Integration Workflow`；3 个用例 | — |
| `__tests__/rulesHotReloadTypes.test.ts` | 测试 | `RulesHotReloadTypes Contracts`；4 个用例 | — |
| `__tests__/useWorkspaceRulesStore.test.ts` | 测试 | `useWorkspaceRulesStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
