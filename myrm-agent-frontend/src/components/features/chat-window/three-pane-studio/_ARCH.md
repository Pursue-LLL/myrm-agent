# chat-window/three-pane-studio/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ContextTreePane.tsx` | 组件 | Visual tree navigator for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite. Renders User Memory, Workspace Resources, and Agent Skills with realtime pulse highlights, expansion toggles, and one-click reference injection into the chat prompt. | ✅ |
| `MiddleContentPane.tsx` | 组件 | Central content explorer for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite. Renders selected context node content, Agent read/write live indicators, metadata attributes, and provides one-click content copying. | ✅ |
| `ThreePaneContextStudio.tsx` | 组件 | Primary studio shell for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite. Features left context tree, middle file/memory content preview, right dual-mode chat/terminal, collapsible panels, and automatic real-time tool highlight event bridging. | ✅ |
| `index.ts` | 入口 | Public API entry point for the three-pane modern studio workbench. | ✅ |
| `threePaneStudioEngine.ts` | 引擎 | Pure computation engine for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite. Operates on immutable context trees, maps Agent file/memory tool paths to tree nodes, computes ancestor expansion chains for instant unfolding, and broadcasts desktop events. | ✅ |
| `threePaneStudioTypes.ts` | 类型 | Unified domain contracts for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite. Powers three-pane visual white-box studio with real-time tool-tree active highlighting, seamless Agent-chat / Terminal toggling, and interactive context exploration. | ✅ |
| `useThreePaneStudioStore.ts` | 状态仓库 | Central reactive dispatcher for Item 198 (P0): ThreePaneContextStudioAndRealtimeToolHighlightSuite. Coordinates context tree state, tool-driven active highlighting, ancestor auto-unfolding, middle-pane file loading, and right-pane Agent-chat/Terminal view toggling. | ✅ |
| `__tests__/ThreePaneContextStudio.test.tsx` | 测试 | `ThreePaneContextStudio Component`；6 个用例 | — |
| `__tests__/threePaneStudioEngine.test.ts` | 测试 | `threePaneStudioEngine`；13 个用例 | — |
| `__tests__/threePaneStudioIntegration.test.tsx` | 测试 | `ThreePaneStudio Integration Linkage`；3 个用例 | — |
| `__tests__/threePaneStudioTypes.test.ts` | 测试 | `ThreePaneStudioTypes Contracts`；3 个用例 | — |
| `__tests__/useThreePaneStudioStore.test.ts` | 测试 | `useThreePaneStudioStore`；7 个用例 | — |

## 依赖

- 项目内：`@/lib/utils`
- 第三方：`lucide-react`、`react`、`zustand`
