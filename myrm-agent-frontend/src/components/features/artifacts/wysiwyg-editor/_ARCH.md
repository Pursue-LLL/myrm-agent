# artifacts/wysiwyg-editor/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个状态仓库、1 个引擎、1 个类型），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `FloatingStyleToolbar.tsx` | 组件 | 导出 `FloatingStyleToolbar`；类型 `FloatingStyleToolbarProps` | — |
| `WysiwygArtifactEditorOverlay.tsx` | 组件 | 导出 `WysiwygArtifactEditorOverlay`；类型 `WysiwygArtifactEditorOverlayProps` | — |
| `ZeroTokenSaveBanner.tsx` | 组件 | 导出 `ZeroTokenSaveBanner`；类型 `ZeroTokenSaveBannerProps` | — |
| `index.ts` | 入口 | 聚合导出 `./wysiwygEditorTypes`、`./wysiwygEditorEngine`、`./useWysiwygEditorStore`、`./FloatingStyleToolbar`、`./ZeroTokenSaveBanner`、`./WysiwygArtifactEditorOverlay` | — |
| `useWysiwygEditorStore.ts` | 状态仓库 | 导出 `useWysiwygEditorStore`；类型 `WysiwygEditorActions`、`WysiwygEditorStore` | — |
| `wysiwygEditorEngine.ts` | 引擎 | 导出 `mapFontSizeToCss`、`buildElementSelector`、`applyTextMutationToHtml`、`mergeStyleObjectToCssString`、`buildZeroTokenCommitReport` | — |
| `wysiwygEditorTypes.ts` | 类型 | 导出类型 `InlineEditMode`、`FontSizeOption`、`InlineElementStyles`、`SelectedDomElementInfo`、`MutationDiffSummary`、`ZeroTokenCommitReport` 等 7 个 | — |
| `__tests__/FloatingStyleToolbar.test.tsx` | 测试 | `FloatingStyleToolbar`；5 个用例 | — |
| `__tests__/ZeroTokenSaveBanner.test.tsx` | 测试 | `ZeroTokenSaveBanner`；2 个用例 | — |
| `__tests__/useWysiwygEditorStore.test.ts` | 测试 | `useWysiwygEditorStore`；7 个用例 | — |
| `__tests__/wysiwygEditorEngine.test.ts` | 测试 | `wysiwygEditorEngine`；6 个用例 | — |
| `__tests__/wysiwygEditorIntegration.test.tsx` | 测试 | `WysiwygArtifactEditor Integration End-to-End`；2 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
