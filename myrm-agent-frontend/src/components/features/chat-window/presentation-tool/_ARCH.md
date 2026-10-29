# chat-window/presentation-tool/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `InteractiveSuggestionChips.tsx` | 组件 | 导出 `InteractiveSuggestionChips` | — |
| `StructuredPresentationCard.tsx` | 组件 | 导出 `StructuredPresentationCard` | — |
| `index.ts` | 入口 | 聚合导出 `./presentationToolTypes`、`./presentationToolEngine`、`./usePresentationToolStore`、`./InteractiveSuggestionChips`、`./StructuredPresentationCard` | — |
| `presentationToolEngine.ts` | 引擎 | 导出 `sanitizePresentationText`、`validateSuggestionChipsPayload`、`resolvePositionalReference` | — |
| `presentationToolTypes.ts` | 类型 | 导出类型 `PresentationToolName`、`SuggestionChipItem`、`ProductPresentationItem`、`ItineraryStepItem`、`ComparisonRowItem`、`PresentationItem` 等 8 个 | — |
| `usePresentationToolStore.ts` | 状态仓库 | 导出 `usePresentationToolStore` | — |
| `__tests__/InteractiveSuggestionChips.test.tsx` | 测试 | `InteractiveSuggestionChips`；3 个用例 | — |
| `__tests__/StructuredPresentationCard.test.tsx` | 测试 | `StructuredPresentationCard`；4 个用例 | — |
| `__tests__/presentationToolEngine.test.ts` | 测试 | `presentationToolEngine`；9 个用例 | — |
| `__tests__/usePresentationToolStore.test.ts` | 测试 | `usePresentationToolStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
