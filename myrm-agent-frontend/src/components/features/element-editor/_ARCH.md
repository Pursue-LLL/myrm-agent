# element-editor/

## 架构概述

8 个源文件（4 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ElementInspectorOverlay.tsx` | 组件 | 导出 `ElementInspectorOverlay` | — |
| `ElementVisualEditorContainer.tsx` | 组件 | 导出 `ElementVisualEditorContainer` | — |
| `InPlaceEditPopover.tsx` | 组件 | 导出 `InPlaceEditPopover` | — |
| `VisualVersionRollbackDeck.tsx` | 组件 | 导出 `VisualVersionRollbackDeck` | — |
| `elementEditorEngine.ts` | 引擎 | 导出 `extractElementInfo`、`buildTargetedMicroPatchPrompt`、`createSnapshot`、`isUndoShortcut`、`isRedoShortcut`、`getDefaultHtmlContent` 等 7 个 | — |
| `elementEditorTypes.ts` | 类型 | 导出类型 `ElementEditorMode`、`BoundingRect`、`InspectorElementInfo`、`EditPromptCategory`、`InPlacePromptPayload`、`SnapshotDiffStats` 等 7 个 | — |
| `index.ts` | 入口 | 聚合导出 `./elementEditorTypes`、`./elementEditorEngine`、`./useElementEditorStore`、`./ElementInspectorOverlay`、`./InPlaceEditPopover`、`./VisualVersionRollbackDeck`、`./ElementVisualEditorContainer` | — |
| `useElementEditorStore.ts` | 状态仓库 | 导出 `useElementEditorStore` | — |
| `__tests__/ElementVisualEditorContainer.test.tsx` | 测试 | `ElementVisualEditorContainer`；4 个用例 | — |
| `__tests__/InPlaceEditPopover.test.tsx` | 测试 | `InPlaceEditPopover`；4 个用例 | — |
| `__tests__/VisualVersionRollbackDeck.test.tsx` | 测试 | `VisualVersionRollbackDeck`；3 个用例 | — |
| `__tests__/elementEditorEngine.test.ts` | 测试 | `elementEditorEngine`；5 个用例 | — |
| `__tests__/useElementEditorStore.test.ts` | 测试 | `useElementEditorStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
