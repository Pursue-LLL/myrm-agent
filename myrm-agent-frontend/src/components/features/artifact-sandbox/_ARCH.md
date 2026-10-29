# artifact-sandbox/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `FinancialSandplayWidget.tsx` | 组件 | 导出 `FinancialSandplayWidget`；类型 `FinancialSandplayWidgetProps` | — |
| `InteractiveArtifactSandbox.tsx` | 组件 | 导出 `InteractiveArtifactSandbox`；类型 `InteractiveArtifactSandboxProps` | — |
| `NewsletterRichStyler.tsx` | 组件 | 导出 `NewsletterRichStyler`；类型 `NewsletterRichStylerProps` | — |
| `artifactSandboxEngine.ts` | 引擎 | 导出 `THEME_DEFINITIONS`、`recordToStyleString`、`compileInlinedHtml`、`buildSafeSandboxIframeSrcDoc`、`bundleSingleFileOfflineHtml`、`calculateFinancialSandplay` | — |
| `artifactSandboxTypes.ts` | 类型 | 导出类型 `ArtifactSandboxMode`、`NewsletterTheme`、`ThemeStyleDefinition`、`InlinerAssetItem`、`InteractiveArtifactItem`、`FinancialSandplayMetrics` 等 8 个 | — |
| `index.ts` | 入口 | 聚合导出 `./artifactSandboxTypes`、`./artifactSandboxEngine`、`./useArtifactSandboxStore`、`./InteractiveArtifactSandbox`、`./NewsletterRichStyler`、`./FinancialSandplayWidget` | — |
| `useArtifactSandboxStore.ts` | 状态仓库 | 导出 `useArtifactSandboxStore`；类型 `ArtifactSandboxStoreState` | — |
| `__tests__/FinancialSandplayWidget.test.tsx` | 测试 | `FinancialSandplayWidget`；4 个用例 | — |
| `__tests__/InteractiveArtifactSandbox.test.tsx` | 测试 | `InteractiveArtifactSandbox`；4 个用例 | — |
| `__tests__/NewsletterRichStyler.test.tsx` | 测试 | `NewsletterRichStyler`；4 个用例 | — |
| `__tests__/artifactSandboxEngine.test.ts` | 测试 | `artifactSandboxEngine`；5 个用例 | — |
| `__tests__/useArtifactSandboxStore.test.ts` | 测试 | `useArtifactSandboxStore`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
