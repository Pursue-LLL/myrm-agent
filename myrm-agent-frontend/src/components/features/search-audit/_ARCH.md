# search-audit/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `SearchAuditDrawer.tsx` | 组件 | 导出 `SearchAuditDrawer`；类型 `SearchAuditDrawerProps` | — |
| `SearchAuditEvidenceBadge.tsx` | 组件 | 导出 `SearchAuditEvidenceBadge`；类型 `SearchAuditEvidenceBadgeProps` | — |
| `index.ts` | 入口 | 聚合导出 `./searchAuditTypes`、`./searchAuditEngine`、`./useSearchAuditStore`、`./SearchAuditDrawer`、`./SearchAuditEvidenceBadge` | — |
| `searchAuditEngine.ts` | 引擎 | 导出 `extractDomain`、`calculateSourceQualityMatrix`、`formatPayloadBytes`、`formatLatency`、`getScoreTierBadgeColor`、`summarizeSearchAuditSession` | — |
| `searchAuditTypes.ts` | 类型 | 导出类型 `SourceTier`、`SourceQualityMatrix`、`SubQueryTrace`、`AuditCitationItem`、`SearchAuditSession` | — |
| `useSearchAuditStore.ts` | 状态仓库 | 导出 `useSearchAuditStore`；类型 `SearchAuditTab`、`SearchAuditStoreState` | — |
| `__tests__/SearchAuditDrawer.test.tsx` | 测试 | `SearchAuditDrawer`；6 个用例 | — |
| `__tests__/SearchAuditEvidenceBadge.test.tsx` | 测试 | `SearchAuditEvidenceBadge`；3 个用例 | — |
| `__tests__/searchAuditEngine.test.ts` | 测试 | `searchAuditEngine`；8 个用例 | — |
| `__tests__/searchAuditIntegration.test.tsx` | 测试 | `SearchAudit Integration Suite`；1 个用例 | — |
| `__tests__/useSearchAuditStore.test.ts` | 测试 | `useSearchAuditStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
