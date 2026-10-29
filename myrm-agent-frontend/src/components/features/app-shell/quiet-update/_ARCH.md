# app-shell/quiet-update/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `QuietMomentUpdateBanner.tsx` | 组件 | 导出 `QuietMomentUpdateBanner`；类型 `QuietMomentUpdateBannerProps` | — |
| `UpdateOfferDismissModal.tsx` | 组件 | 导出 `UpdateOfferDismissModal`；类型 `UpdateOfferDismissModalProps` | — |
| `index.ts` | 入口 | 聚合导出 `./quietMomentUpdateTypes`、`./quietMomentUpdateEngine`、`./useQuietMomentUpdateStore`、`./QuietMomentUpdateBanner`、`./UpdateOfferDismissModal` | — |
| `quietMomentUpdateEngine.ts` | 引擎 | 导出 `DEFAULT_TYPING_GRACE_MS`、`DEFAULT_FRESH_SNAPSHOT_TTL_MS`、`DEFAULT_EMPTY_SNAPSHOT_TTL_MS`、`DEFAULT_OFFER_COOLDOWN_MS`、`evaluateAppQuietness`、`isSnapshotFresh` 等 10 个；类型 `EligibilityEvaluationParams` | — |
| `quietMomentUpdateTypes.ts` | 类型 | 导出类型 `UpdateOfferStatus`、`QuietMomentBlockReason`、`ConnectionMode`、`QuietMomentContext`、`UpdateAvailabilitySnapshot`、`DismissedVersionRecord` 等 8 个 | — |
| `useQuietMomentUpdateStore.ts` | 状态仓库 | 导出 `useQuietMomentUpdateStore`；类型 `QuietMomentUpdateState` | — |
| `__tests__/QuietMomentUpdateBanner.test.tsx` | 测试 | `QuietMomentUpdateBanner`；6 个用例 | — |
| `__tests__/UpdateOfferDismissModal.test.tsx` | 测试 | `UpdateOfferDismissModal`；6 个用例 | — |
| `__tests__/quietMomentUpdateEngine.test.ts` | 测试 | `quietMomentUpdateEngine`；17 个用例 | — |
| `__tests__/quietMomentUpdateIntegration.test.tsx` | 测试 | `QuietMomentUpdate Integration Flow`；1 个用例 | — |
| `__tests__/useQuietMomentUpdateStore.test.ts` | 测试 | `useQuietMomentUpdateStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
