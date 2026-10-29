# turn-lineage/

## 架构概述

8 个源文件（4 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），6 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `TurnLineageFilterBar.tsx` | 组件 | 导出 `TurnLineageFilterBar` | — |
| `TurnOriginBadge.tsx` | 组件 | 导出 `TurnOriginBadge` | — |
| `TurnProvenanceHoverCard.tsx` | 组件 | 导出 `TurnProvenanceHoverCard` | — |
| `TurnTimelineAuditRail.tsx` | 组件 | 导出 `TurnTimelineAuditRail` | — |
| `index.ts` | 入口 | 聚合导出 `./turnLineageTypes`、`./turnLineageEngine`、`./useTurnLineageStore`、`./TurnProvenanceHoverCard`、`./TurnOriginBadge`、`./TurnLineageFilterBar`、`./TurnTimelineAuditRail` | — |
| `turnLineageEngine.ts` | 引擎 | 导出 `ORIGIN_VISUAL_CONFIG`、`getOriginVisualTheme`、`filterTurns`、`traceCausalityLineage`、`getDefaultTurns` | — |
| `turnLineageTypes.ts` | 类型 | 导出类型 `TurnOriginType`、`TurnProvenanceMeta`、`ChatTurnItem`、`LineageFilterMode`、`OriginVisualTheme` | — |
| `useTurnLineageStore.ts` | 状态仓库 | 导出 `useTurnLineageStore` | — |
| `__tests__/TurnLineageFilterBar.test.tsx` | 测试 | `TurnLineageFilterBar 组件单测`；3 个用例 | — |
| `__tests__/TurnOriginBadge.test.tsx` | 测试 | `TurnOriginBadge`；4 个用例 | — |
| `__tests__/TurnTimelineAuditRail.test.tsx` | 测试 | `TurnTimelineAuditRail 组件单测`；4 个用例 | — |
| `__tests__/turnFixtures.ts` | 测试 | 0 个用例 | — |
| `__tests__/turnLineageEngine.test.ts` | 测试 | `turnLineageEngine`；4 个用例 | — |
| `__tests__/useTurnLineageStore.test.ts` | 测试 | `useTurnLineageStore`；4 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
