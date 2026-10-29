# insitu-annotation/

## 架构概述

8 个源文件（4 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `InSituBatchCommentRail.tsx` | 组件 | 导出 `InSituBatchCommentRail` | — |
| `InSituCanvasContainer.tsx` | 组件 | 导出 `InSituCanvasContainer` | — |
| `InSituCommentPinLayer.tsx` | 组件 | 导出 `InSituCommentPinLayer` | — |
| `InSituPropertyInspector.tsx` | 组件 | 导出 `InSituPropertyInspector` | — |
| `index.ts` | 入口 | 聚合导出 `./insituAnnotationTypes`、`./insituAnnotationEngine`、`./useInsituAnnotationStore`、`./InSituPropertyInspector`、`./InSituCommentPinLayer`、`./InSituBatchCommentRail`、`./InSituCanvasContainer` | — |
| `insituAnnotationEngine.ts` | 引擎 | 导出 `generateCssFromPatches`、`compileBatchAnnotationsPrompt`、`buildBatchAnnotationPayload` | — |
| `insituAnnotationTypes.ts` | 类型 | 导出类型 `CanvasInteractionMode`、`ElementStylePatch`、`VisualCommentPin`、`BatchAnnotationPayload`、`InSituInspectionTarget` | — |
| `useInsituAnnotationStore.ts` | 状态仓库 | 导出 `useInsituAnnotationStore` | — |
| `__tests__/InSituBatchCommentRail.test.tsx` | 测试 | `InSituBatchCommentRail 组件单测`；4 个用例 | — |
| `__tests__/InSituCommentPinLayer.test.tsx` | 测试 | `InSituCommentPinLayer 组件单测`；3 个用例 | — |
| `__tests__/InSituPropertyInspector.test.tsx` | 测试 | `InSituPropertyInspector 组件单测`；4 个用例 | — |
| `__tests__/insituAnnotationEngine.test.ts` | 测试 | `insituAnnotationEngine 核心函数单测`；3 个用例 | — |
| `__tests__/useInsituAnnotationStore.test.ts` | 测试 | `useInsituAnnotationStore 状态管理单测`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
