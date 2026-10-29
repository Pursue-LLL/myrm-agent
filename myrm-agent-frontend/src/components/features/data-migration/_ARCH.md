# data-migration/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `DataMigrationSection.tsx` | 组件 | 导出 `DataMigrationSection`；类型 `DataMigrationSectionProps` | — |
| `MigrationReconciliationModal.tsx` | 组件 | 导出 `MigrationReconciliationModal`；类型 `MigrationReconciliationModalProps` | — |
| `MigrationSilentToast.tsx` | 组件 | 导出 `MigrationSilentToast`；类型 `MigrationSilentToastProps` | — |
| `dataMigrationEngine.ts` | 引擎 | 导出 `normalizeCronExpression`、`normalizeMcpConfig`、`generateAssetFingerprint`、`buildReconciliationReport`、`applyConflictResolution`、`formatSourceTypeLabel` | — |
| `dataMigrationTypes.ts` | 类型 | 导出类型 `MigrationSourceType`、`ConflictStrategy`、`LegacyTaskItem`、`LegacyCronJob`、`LegacyMemoryItem`、`LegacyMcpConfig` 等 11 个 | — |
| `index.ts` | 入口 | 聚合导出 `./dataMigrationTypes`、`./dataMigrationEngine`、`./useDataMigrationStore`、`./DataMigrationSection`、`./MigrationReconciliationModal`、`./MigrationSilentToast` | — |
| `useDataMigrationStore.ts` | 状态仓库 | 导出 `useDataMigrationStore`；类型 `DataMigrationStoreState` | — |
| `__tests__/DataMigrationSection.test.tsx` | 测试 | `DataMigrationSection`；5 个用例 | — |
| `__tests__/MigrationReconciliationModal.test.tsx` | 测试 | `MigrationReconciliationModal`；5 个用例 | — |
| `__tests__/dataMigrationEngine.test.ts` | 测试 | `dataMigrationEngine`；6 个用例 | — |
| `__tests__/dataMigrationIntegration.test.tsx` | 测试 | `DataMigration Integration End-to-End`；3 个用例 | — |
| `__tests__/useDataMigrationStore.test.ts` | 测试 | `useDataMigrationStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
