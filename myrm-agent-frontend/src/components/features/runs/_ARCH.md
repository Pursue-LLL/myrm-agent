# runs/

## 架构概述

Unified Runs Hub：聚合 Cron / Kanban / Shell 后台任务的运行历史，支持状态与来源筛选、分页加载与详情展开。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| ---- | ---- | ---- | ---- |
| `RunsHub.tsx` | 核心 | 运行列表 UI、筛选 Tabs、RunRow 展开详情、加载失败态 | — |
| `__tests__/RunsHub.test.tsx` | 测试 | error/retry、emptyFiltered、degraded、loadMore toast、badge | — |
| `__tests__/runsLocales.test.ts` | 测试 | 五语 `runs` namespace key 完整性 | — |

## 路由

| 路径 | 页面 |
| ---- | ---- |
| `/runs` | [src/app/runs/page.tsx](../../../app/runs/page.tsx) |

## 依赖

- `@/services/runs` — `listUnifiedRuns`、`UnifiedRun` 类型（POS: 统一运行历史 REST 客户端）
- `@/components/primitives/*` — Button、Tabs、Skeleton
- `locales/namespaces/*/runs.json` — 运行时 `runs` namespace（五语：en/zh/ja/ko/de）；译者 SSOT 为 `locales/{lang}.json`，改文案后跑 `bun run i18n:split`

## 约束

- 文案禁止硬编码；使用 `useTranslations('runs')`
- `has_execution_steps` 表示 cron run metadata 含 progressSteps（非 chat transcript）
- 首屏加载失败：inline error + retry（不用 toast，避免与 inline 重复）
- 分页 loadMore 失败：toast.error（列表仍可见）
- 筛选无结果：显示 `emptyFiltered`；无筛选真空：显示 `empty`
- 部分数据源不可用：`degraded` banner（server 返回 `failed_sources`）
- 筛选切换时使用 requestSeq 丢弃过期响应，避免竞态覆盖；reload 期间列表半透明 + 禁用交互
- 新增子组件时保持本目录 `_ARCH.md` 与 [features/_ARCH.md](../_ARCH.md) 同步
