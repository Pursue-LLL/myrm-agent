# chat-window/cli-passthrough/

## 架构概述

5 个源文件（1 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CliCommandPreviewDrawer.tsx` | 组件 | Primary drawer UI for Item 194 (P0): DirectCliPassThroughWithContextVisibilitySwitchSuite. Renders command output above message input, highlighting context visibility ('!' vs '!!'). | ✅ |
| `cliPassthroughEngine.ts` | 引擎 | Pure computation engine for Item 194 (P0): DirectCliPassThroughWithContextVisibilitySwitchSuite. Parses '!' vs '!!' prefixes, audits security barriers, and formats context injection blocks. | ✅ |
| `cliPassthroughTypes.ts` | 类型 | Unified types for Item 194 (P0): DirectCliPassThroughWithContextVisibilitySwitchSuite. Distinguishes '!cmd' (injected into context for LLM reasoning) from '!!cmd' (user inspection only, 0 token waste, strictly excluded from context). | ✅ |
| `index.ts` | 入口 | Public barrel export module for CLI pass-through with context visibility switch ('!' vs '!!'). | ✅ |
| `useCliPassthroughStore.ts` | 状态仓库 | Central reactive dispatcher for Item 194 (P0). Orchestrates CLI command parsing, safety guard gating, output collection, and context-visibility switching between '!cmd' and '!!cmd'. | ✅ |
| `__tests__/CliCommandPreviewDrawer.test.tsx` | 测试 | `CliCommandPreviewDrawer`；7 个用例 | — |
| `__tests__/cliPassthroughEngine.test.ts` | 测试 | `cliPassthroughEngine`；8 个用例 | — |
| `__tests__/cliPassthroughIntegration.test.ts` | 测试 | `cliPassthroughIntegration`；4 个用例 | — |
| `__tests__/cliPassthroughTypes.test.ts` | 测试 | `cliPassthroughTypes`；1 个用例 | — |
| `__tests__/useCliPassthroughStore.test.ts` | 测试 | `useCliPassthroughStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
