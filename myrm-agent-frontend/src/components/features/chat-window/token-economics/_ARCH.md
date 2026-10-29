# chat-window/token-economics/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ProviderBalanceModal.tsx` | 组件 | Primary modal for Item 193 (P1). Displays live balance probes, watermark levels, and quota consumption across mainstream LLM providers. | ✅ |
| `SessionTokenCapsule.tsx` | 组件 | Primary header/toolbar capsule for Item 193 (P1). Displays real-time session tokens and currency cost projections, with quick entry to the provider balance probe modal. | ✅ |
| `index.ts` | 入口 | Public barrel export module for session token economics & provider balance inspection. | ✅ |
| `tokenEconomicsEngine.ts` | 引擎 | Pure computation engine for Item 193 (P1): SessionTokenEconomicsAndProviderBalanceCardSuite. Calculates real-time model token fees, formats currencies, and evaluates provider watermarks. | ✅ |
| `tokenEconomicsTypes.ts` | 类型 | Unified types for Item 193 (P1): SessionTokenEconomicsAndProviderBalanceCardSuite. Eliminates LLM blackbox anxiety by providing real-time session token metering, cost projection, and upstream provider balance self-inspection. | ✅ |
| `useTokenEconomicsStore.ts` | 状态仓库 | Central reactive dispatcher for Item 193 (P1). Aggregates live token usage per chat session, computes pricing projections, and maintains provider account balances with live probing capabilities. | ✅ |
| `__tests__/ProviderBalanceModal.test.tsx` | 测试 | `ProviderBalanceModal`；5 个用例 | — |
| `__tests__/SessionTokenCapsule.test.tsx` | 测试 | `SessionTokenCapsule`；5 个用例 | — |
| `__tests__/tokenEconomicsEngine.test.ts` | 测试 | `tokenEconomicsEngine`；13 个用例 | — |
| `__tests__/tokenEconomicsTypes.test.ts` | 测试 | `tokenEconomicsTypes`；1 个用例 | — |
| `__tests__/useTokenEconomicsStore.test.ts` | 测试 | `useTokenEconomicsStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`next`、`react`、`zustand`
