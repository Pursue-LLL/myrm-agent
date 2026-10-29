# theme/layer-invariants/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `PrebakedBaselineDiffModal.tsx` | 组件 | 导出 `PrebakedBaselineDiffModal`；类型 `PrebakedBaselineDiffModalProps` | — |
| `ThemeLayerDirectionInspectorCard.tsx` | 组件 | 导出 `ThemeLayerDirectionInspectorCard`；类型 `ThemeLayerDirectionInspectorCardProps` | — |
| `index.ts` | 入口 | 聚合导出 `./themeLayerInvariantTypes`、`./themeLayerInvariantEngine`、`./useThemeLayerInvariantStore`、`./ThemeLayerDirectionInspectorCard`、`./PrebakedBaselineDiffModal` | — |
| `themeLayerInvariantEngine.ts` | 引擎 | 导出 `parseHexToRgb`、`calculateHexLightness`、`evaluateLayerDirection`、`evaluateThemeInvariantSuite`、`compareWithPrebakedBaseline` | — |
| `themeLayerInvariantTypes.ts` | 类型 | 导出类型 `ThemeMode`、`LayerDirectionEvaluation`、`PrebakedThemeBaseline`、`ThemeInvariantSuiteReport`、`ThemeLayerInvariantState` | — |
| `useThemeLayerInvariantStore.ts` | 状态仓库 | 导出 `useThemeLayerInvariantStore`；类型 `ThemeLayerInvariantActions`、`ThemeLayerInvariantStore` | — |
| `__tests__/PrebakedBaselineDiffModal.test.tsx` | 测试 | `PrebakedBaselineDiffModal`；4 个用例 | — |
| `__tests__/ThemeLayerDirectionInspectorCard.test.tsx` | 测试 | `ThemeLayerDirectionInspectorCard`；3 个用例 | — |
| `__tests__/themeLayerInvariantEngine.test.ts` | 测试 | `themeLayerInvariantEngine`；6 个用例 | — |
| `__tests__/themeLayerInvariantIntegration.test.tsx` | 测试 | `ThemeLayerInvariant Integration End-to-End`；1 个用例 | — |
| `__tests__/useThemeLayerInvariantStore.test.ts` | 测试 | `useThemeLayerInvariantStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
