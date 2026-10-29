# threejs-sandbox/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ThreeJsCanvasViewer.tsx` | 组件 | 导出 `ThreeJsCanvasViewer` | — |
| `ThreeJsConsoleDrawer.tsx` | 组件 | 导出 `ThreeJsConsoleDrawer` | — |
| `ThreeJsPerformancePanel.tsx` | 组件 | 导出 `ThreeJsPerformancePanel` | — |
| `index.ts` | 入口 | 聚合导出 `./threeJsTypes`、`./threeJsSandboxEngine`、`./useThreeJsSandboxStore`、`./ThreeJsPerformancePanel`、`./ThreeJsConsoleDrawer`、`./ThreeJsCanvasViewer` | — |
| `threeJsSandboxEngine.ts` | 引擎 | 导出 `buildThreeJsSandboxHtml`、`buildWebGLSelfHealingDossier`、`resolveCameraModeAction` | — |
| `threeJsTypes.ts` | 类型 | 导出类型 `SandboxCameraMode`、`SandboxViewportMode`、`WebGLPerformanceMetrics`、`WebGLLogLevel`、`WebGLLogEntry`、`WebGLSelfHealingDossier` 等 7 个 | — |
| `useThreeJsSandboxStore.ts` | 状态仓库 | 导出 `useThreeJsSandboxStore` | — |
| `__tests__/ThreeJsCanvasViewer.test.tsx` | 测试 | `ThreeJsCanvasViewer 核心容器组件单测`；5 个用例 | — |
| `__tests__/ThreeJsConsoleDrawer.test.tsx` | 测试 | `ThreeJsConsoleDrawer 组件单测`；5 个用例 | — |
| `__tests__/ThreeJsPerformancePanel.test.tsx` | 测试 | `ThreeJsPerformancePanel 组件单测`；3 个用例 | — |
| `__tests__/threeJsSandboxEngine.test.ts` | 测试 | `threeJsSandboxEngine 核心函数单测`；3 个用例 | — |
| `__tests__/useThreeJsSandboxStore.test.ts` | 测试 | `useThreeJsSandboxStore 状态管理单测`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
