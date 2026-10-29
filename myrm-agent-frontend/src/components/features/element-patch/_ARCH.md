# element-patch/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ElementAnnotationPinOverlay.tsx` | 组件 | 导出 `ElementAnnotationPinOverlay`；类型 `ElementAnnotationPinOverlayProps` | — |
| `StagedAnnotationsDrawer.tsx` | 组件 | 导出 `StagedAnnotationsDrawer`；类型 `StagedAnnotationsDrawerProps` | — |
| `SurgicalPatchCard.tsx` | 组件 | 导出 `SurgicalPatchCard`；类型 `SurgicalPatchCardProps` | — |
| `elementPatchEngine.ts` | 引擎 | 导出 `generateElementSelector`、`buildSurgicalPatchPromptDirective`、`createStagedBatchPayload`、`calculateBatchResolveSummary`、`formatAnnotationStatus` | — |
| `elementPatchTypes.ts` | 类型 | 导出类型 `AnnotationStatus`、`ElementBoundingBox`、`ElementAnnotationItem`、`SurgicalPatchScope`、`StagedBatchPayload`、`AnnotationResolveSummary` | — |
| `index.ts` | 入口 | 聚合导出 `./elementPatchTypes`、`./elementPatchEngine`、`./useElementPatchStore`、`./StagedAnnotationsDrawer`、`./ElementAnnotationPinOverlay`、`./SurgicalPatchCard` | — |
| `useElementPatchStore.ts` | 状态仓库 | 导出 `useElementPatchStore`；类型 `ElementPatchStoreState` | — |
| `__tests__/ElementAnnotationPinOverlay.test.tsx` | 测试 | `ElementAnnotationPinOverlay`；4 个用例 | — |
| `__tests__/StagedAnnotationsDrawer.test.tsx` | 测试 | `StagedAnnotationsDrawer`；6 个用例 | — |
| `__tests__/elementPatchEngine.test.ts` | 测试 | `elementPatchEngine`；6 个用例 | — |
| `__tests__/elementPatchIntegration.test.tsx` | 测试 | `ElementPatch Integration Suite`；1 个用例 | — |
| `__tests__/useElementPatchStore.test.ts` | 测试 | `useElementPatchStore`；7 个用例 | — |

## 依赖

- 项目内：`@/lib/utils`
- 第三方：`lucide-react`、`react`、`zustand`
