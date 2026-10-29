# chat-window/lane-gradient/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AlwaysVisibleLaneIndicator.tsx` | 组件 | Persistent visual indicator solving Item 188. Answers the user's immediate question: "What lane am I in, and what can/cannot this lane do right now?" | ✅ |
| `LaneGraduationPromptDialog.tsx` | 组件 | Implementation for Item 188 in-session auto-graduation. Intercepts write/shell triggers in Chat Lane and seamlessly upgrades the session to Workspace Lane while fully preserving conversation history and context. | ✅ |
| `index.ts` | 入口 | Public entrypoint for lane semantic gradient, indicators, and auto-graduation dialog. | ✅ |
| `laneSemanticEngine.ts` | 引擎 | Pure computation engine for Item 188: ChatLaneVsWorkspaceLaneSemanticGradientAndAutoGraduationSuite. Resolves authoritative lane specs from heterogeneous chat state and performs deterministic in-session intent detection for boundary-crossing triggers without side effects. | ✅ |
| `laneSemanticTypes.ts` | 类型 | Unified contract for Item 188: ChatLaneVsWorkspaceLaneSemanticGradientAndAutoGraduationSuite. Establishes an authoritative two-lane paradigm ('chat' vs 'workspace') across 3 runtime modes, eradicating ambiguous modal states and governing in-session auto-graduation triggers. | ✅ |
| `useLaneSemanticStore.ts` | 状态仓库 | Bridges user boundary crossings to concrete chat store actions. Seamlessly upgrades an in-flight conversation from Chat Lane to Workspace Lane without dropping messages or resetting history. | ✅ |
| `__tests__/AlwaysVisibleLaneIndicator.test.tsx` | 测试 | `AlwaysVisibleLaneIndicator`；4 个用例 | — |
| `__tests__/LaneGraduationPromptDialog.test.tsx` | 测试 | `LaneGraduationPromptDialog`；5 个用例 | — |
| `__tests__/laneSemanticEngine.test.ts` | 测试 | `laneSemanticEngine`；12 个用例 | — |
| `__tests__/laneSemanticTypes.test.ts` | 测试 | `laneSemanticTypes`；3 个用例 | — |
| `__tests__/useLaneSemanticStore.test.ts` | 测试 | `useLaneSemanticStore`；7 个用例 | — |

## 依赖

- 项目内：`@/store/useChatStore`
- 第三方：`lucide-react`、`react`、`zustand`
