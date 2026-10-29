# chat-window/session-branch-archive/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `SessionBranchArchiveModal.tsx` | 组件 | Management modal for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite. Renders read-only snapshots, branch tree navigation, token hygiene metrics, and allows users to inspect or remove historic milestone archives. | ✅ |
| `SessionRuleAnchorHeader.tsx` | 组件 | Visual reassurance header for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite. Visually separates "Rules in Files" from "Process in Session", eliminating user fear of context loss and providing one-click clean restarts (/new) and branch exploration entry points. | ✅ |
| `index.ts` | 入口 | Public API entry point for session branch archiving, rule-preserved restarts, and exploration trees. | ✅ |
| `sessionBranchArchiveEngine.ts` | 引擎 | Pure computation engine for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite. Operates on immutable branch trees, constructs read-only session snapshots, computes context hygiene metrics, and broadcasts session lifecycle events. | ✅ |
| `sessionBranchArchiveTypes.ts` | 类型 | Unified contracts for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite. Embodies the "Rules in Files, Process in Session" philosophy, enabling zero-anxiety /new clean restarts, read-only session snapshot archiving, and exploration tree branching. | ✅ |
| `useSessionBranchArchiveStore.ts` | 状态仓库 | Central reactive dispatcher for Item 200 (P1): SessionBranchArchiveAndRulePreservedResetSuite. Manages read-only archived snapshots, zero-anxiety /new clean restarts, rule version persistence, and exploration branch tree state. | ✅ |
| `__tests__/SessionRuleAnchorHeader.test.tsx` | 测试 | `SessionRuleAnchorHeader Component`；4 个用例 | — |
| `__tests__/sessionBranchArchiveEngine.test.ts` | 测试 | `sessionBranchArchiveEngine`；10 个用例 | — |
| `__tests__/sessionBranchArchiveIntegration.test.tsx` | 测试 | `SessionBranchArchive Integration Workflow`；2 个用例 | — |
| `__tests__/sessionBranchArchiveTypes.test.ts` | 测试 | `SessionBranchArchiveTypes Contracts`；4 个用例 | — |
| `__tests__/useSessionBranchArchiveStore.test.ts` | 测试 | `useSessionBranchArchiveStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
