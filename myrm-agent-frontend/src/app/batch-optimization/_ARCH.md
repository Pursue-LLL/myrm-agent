# app/batch-optimization/

## 架构概述

批量技能优化 WebUI 薄壳路由。列表/创建经 `apiRequest` 直调 `/batch-optimization/tasks`；cancel/rollback 经 `@/services/skill-optimization.ts`；类型与统计工具在 `@/lib/batch-optimization.ts`。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `layout.tsx` | 布局 | 页面 metadata（`selectLocalizedText`） |
| `page.tsx` | 核心 | 列表、创建、统计卡片、cancel+rollback 对话框（905 行，待下沉 `features/`） |
| `[batchId]/page.tsx` | 核心 | 任务详情、审计、rollback/cancel 操作 |

## 依赖

- `@/components/features/skills/*` — 未下沉；止损链核心组件在 Settings→技能
- `@/lib/api`（`apiRequest`）— 列表 GET、创建 POST `/batch-optimization/tasks`
- `@/services/skill-optimization.ts` — `cancelBatchTask` / `rollbackBatchTask`
- `@/lib/batch-optimization.ts` — 类型、进度/统计/format 工具
- `locales/*` → `settings.skillOptimization.batchPage`（dialog/cancel toast 含 `cancelRollbackFailed`）+ `localizeReactNode` 渲染 shell 双语源串

## 约束

- 见父级 [`app/_ARCH.md`](../_ARCH.md)：单文件 >600 行应迁至 `features/batch-optimization/`。
