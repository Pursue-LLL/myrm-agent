# chat-window/context-hud/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CacheAttributionPopover.tsx` | 组件 | Primary diagnostic modal for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite. Explains cache miss root causes, provides actionable prefix guidance, and enables 1-click compaction. | ✅ |
| `ContextWatermarkHud.tsx` | 组件 | Primary HUD capsule for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite. Renders the 6 key numbers: Input tokens (↑), Output tokens (↓), Read cache tokens (R K), Cache hit rate (CH%), Watermark %, and Auto-compact status badge. | ✅ |
| `contextHudEngine.ts` | 引擎 | Pure computation engine for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite. Computes 6-metric HUD telemetry, evaluates watermark thresholds, and performs heuristic root-cause attribution for prompt cache misses. | ✅ |
| `contextHudTypes.ts` | 类型 | Unified types for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite. Powers the 6-metrics health HUD and prompt cache attribution diagnostics (Input tokens, Output tokens, Cached read tokens, Cache hit rate, Watermark %, Auto-compact). | ✅ |
| `index.ts` | 入口 | Public barrel export module for context watermark telemetries & prompt cache diagnostics. | ✅ |
| `useContextHudStore.ts` | 状态仓库 | Central reactive dispatcher for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite. Manages 6-metric telemetry per chat session, watermark warnings, and cache diagnostics. | ✅ |
| `__tests__/CacheAttributionPopover.test.tsx` | 测试 | `CacheAttributionPopover`；6 个用例 | — |
| `__tests__/ContextWatermarkHud.test.tsx` | 测试 | `ContextWatermarkHud`；5 个用例 | — |
| `__tests__/contextHudEngine.test.ts` | 测试 | `contextHudEngine`；15 个用例 | — |
| `__tests__/contextHudTypes.test.ts` | 测试 | `contextHudTypes`；1 个用例 | — |
| `__tests__/useContextHudStore.test.ts` | 测试 | `useContextHudStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
