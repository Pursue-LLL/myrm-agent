# projects/ 模块架构

## 架构概述

项目域仪表盘 UI：聚合 Kanban、Cron、Artifacts 等持久化工作流入口，展示轻量统计并导航至对应设置页或功能路由。页面壳在 `src/app/projects/page.tsx`，本目录仅承载仪表盘组件。

## 文件清单

| 文件 | 职责 | I/O/P |
|------|------|-------|
| `ProjectsDashboard.tsx` | 项目卡片网格：并行拉取看板/定时任务计数，跳转设置页或 `/artifacts` | ✅ |

## 依赖

- `@/services/kanban` — `listBoards`
- `@/services/cron` — `listCronJobs`
- `next-intl` — `projects` namespace（`locales/*.json`）

## 约束

- 禁止在本目录放 HTTP 客户端；统计 API 调用经 `@/services/*`
- 新增项目入口时同步更新 `PROJECT_ENTRIES` 与 `locales` 文案
