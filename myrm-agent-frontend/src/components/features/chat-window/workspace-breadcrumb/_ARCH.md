# chat-window/workspace-breadcrumb/

## 架构概述

5 个源文件（1 个组件、1 个入口、1 个状态仓库、1 个引擎、1 个类型），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `WorkspaceBreadcrumbBar.tsx` | 组件 | Visual presentation bar for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite. Renders structured breadcrumb segments, sandbox status badge, one-click clipboard copy, and desktop Finder / Terminal bridge triggers to eliminate artifact landing blind spots. | ✅ |
| `index.ts` | 入口 | Unified entry point providing path parsing engines, Zustand store, and UI bar. | ✅ |
| `useWorkspaceBreadcrumbStore.ts` | 状态仓库 | Central reactive dispatcher for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite. Manages active session workspace physical paths, copy status feedback, and desktop Finder/Terminal bridge invocation. | ✅ |
| `workspaceBreadcrumbEngine.ts` | 引擎 | Pure computation engine for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite. Normalizes multi-platform workspace paths, splits hierarchical breadcrumb segments, and dispatches desktop file manager / terminal bridge events. | ✅ |
| `workspaceBreadcrumbTypes.ts` | 类型 | Unified types for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite. Resolves artifact landing anxiety by visualizing physical project paths, supporting Finder/Explorer reveals, path copying, and terminal bridging. | ✅ |
| `__tests__/WorkspaceBreadcrumbBar.test.tsx` | 测试 | `WorkspaceBreadcrumbBar Component`；5 个用例 | — |
| `__tests__/useWorkspaceBreadcrumbStore.test.ts` | 测试 | `useWorkspaceBreadcrumbStore`；6 个用例 | — |
| `__tests__/workspaceBreadcrumbEngine.test.ts` | 测试 | `workspaceBreadcrumbEngine`；10 个用例 | — |
| `__tests__/workspaceBreadcrumbIntegration.test.tsx` | 测试 | `WorkspaceBreadcrumb Integration Workflow`；2 个用例 | — |
| `__tests__/workspaceBreadcrumbTypes.test.ts` | 测试 | `WorkspaceBreadcrumbTypes Contracts`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
