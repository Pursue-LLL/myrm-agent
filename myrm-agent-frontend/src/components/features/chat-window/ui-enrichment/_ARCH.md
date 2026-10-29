# chat-window/ui-enrichment/

## 架构概述

5 个源文件（1 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AntiTamperEnrichedCard.tsx` | 组件 | 导出 `AntiTamperEnrichedCard` | — |
| `index.ts` | 入口 | 聚合导出 `./uiEnrichmentTypes`、`./uiEnrichmentEngine`、`./useUiEnrichmentStore`、`./AntiTamperEnrichedCard` | — |
| `uiEnrichmentEngine.ts` | 引擎 | 导出 `sanitizeNoteCurrencyAndTemporalConflict`、`enrichModelJudgmentsWithAuthoritativeFacts` | — |
| `uiEnrichmentTypes.ts` | 类型 | 导出类型 `AuthoritativeFactRecord`、`ModelJudgmentInput`、`EnrichedUiCardItem`、`EnrichmentAuditLog`、`EnrichedPresentationResult` | — |
| `useUiEnrichmentStore.ts` | 状态仓库 | 导出 `useUiEnrichmentStore` | — |
| `__tests__/AntiTamperEnrichedCard.test.tsx` | 测试 | `AntiTamperEnrichedCard`；3 个用例 | — |
| `__tests__/integration.test.tsx` | 测试 | `UI Enrichment & Anti-Tamper End-to-End Integration`；1 个用例 | — |
| `__tests__/uiEnrichmentEngine.test.ts` | 测试 | `uiEnrichmentEngine`；4 个用例 | — |
| `__tests__/useUiEnrichmentStore.test.ts` | 测试 | `useUiEnrichmentStore`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
