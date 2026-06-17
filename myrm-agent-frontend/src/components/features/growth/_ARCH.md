# growth/

## 架构概述

用户增长仪表盘模块。展示记忆/技能/活跃度 KPI、智能节省摘要、活动热力图、健康雷达和技能演进时间线。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `GrowthDashboard.tsx` | 核心 | 仪表盘主页面，含时间范围选择器(7/30/90D)、KPI 卡片、Savings 卡片、子组件编排 | ✅ |
| `ActivityHeatmap.tsx` | 组件 | GitHub 风格的活动热力图渲染 | ✅ |
| `DailyJournal.tsx` | 组件 | 日志视图（按天展示对话摘要） | ✅ |
| `HealthRadar.tsx` | 组件 | 记忆健康雷达图（多维度可视化） | ✅ |
| `SkillEventList.tsx` | 组件 | 技能演进事件列表 | ✅ |

## 依赖

- `@/services/statistics` — GrowthDashboardData、CostSummary DTO
- `@/components/primitives/*` — Card、Tabs、Button
- `@/lib/utils/classnameUtils` — cn()
- `@/lib/api` — showApiError
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
