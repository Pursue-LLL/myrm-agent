# chat-window/graceful-degradation/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `LiveComponentHealthIndicator.tsx` | 组件 | 导出 `LiveComponentHealthIndicator` | — |
| `NonIntrusiveFallbackPillBadge.tsx` | 组件 | 导出 `NonIntrusiveFallbackPillBadge` | — |
| `gracefulDegradationEngine.ts` | 引擎 | 导出 `computeOverallSystemHealth`、`formatLatency`、`generateFallbackPillText`、`getCircuitBreakerLabel` | — |
| `gracefulDegradationTypes.ts` | 类型 | 导出类型 `DegradationSeverity`、`DependencyComponentType`、`CircuitBreakerStatus`、`ComponentHealthRecord`、`DegradationEvent`、`GlobalSystemHealthStatus` 等 7 个 | — |
| `index.ts` | 入口 | 聚合导出 `./gracefulDegradationTypes`、`./gracefulDegradationEngine`、`./useGracefulDegradationStore`、`./NonIntrusiveFallbackPillBadge`、`./LiveComponentHealthIndicator` | — |
| `useGracefulDegradationStore.ts` | 状态仓库 | 导出 `useGracefulDegradationStore` | — |
| `__tests__/LiveComponentHealthIndicator.test.tsx` | 测试 | `LiveComponentHealthIndicator`；4 个用例 | — |
| `__tests__/NonIntrusiveFallbackPillBadge.test.tsx` | 测试 | `NonIntrusiveFallbackPillBadge`；3 个用例 | — |
| `__tests__/gracefulDegradationEngine.test.ts` | 测试 | `gracefulDegradationEngine`；12 个用例 | — |
| `__tests__/useGracefulDegradationStore.test.ts` | 测试 | `useGracefulDegradationStore`；3 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
