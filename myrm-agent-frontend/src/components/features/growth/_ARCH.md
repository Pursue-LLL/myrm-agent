# growth/

## 架构概述

学习旅程统一模块（路由 `/journey`，旧 `/growth` 自动重定向）。展示记忆/技能/活跃度 KPI、智能节省摘要、活动热力图、健康雷达、知识图谱、技能使用趋势、技能演进时间线和行为模式发现复盘面板。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `GrowthDashboard.tsx` | 核心 | 仪表盘主页面，含时间范围选择器(7/30/90D)、KPI 卡片、Savings 卡片、Tabs 编排（Overview / Evolution Digest / Knowledge Graph / Skill Trends / Daily Review） | ✅ |
| `SkillTrendChart.tsx` | 组件 | 技能使用趋势图。支持技能选择、三维度切换（成功率/耗时/次数）、日粒度柱状图 | ✅ |
| `PatternDigestPanel.tsx` | 组件 | 行为模式发现复盘面板。展示 Pattern Discovery 历史结果卡片、空状态引导、手动触发分析按钮 | ✅ |
| `ActivityHeatmap.tsx` | 组件 | GitHub 风格的活动热力图渲染 | ✅ |
| `DailyJournal.tsx` | 组件 | 日志视图（按天展示对话摘要） | ✅ |
| `DailyWrapCard.tsx` | 组件 | AI 日报摘要卡片（Daily Wrap），由 DailyJournal 使用 | ✅ |
| `HealthRadar.tsx` | 组件 | 记忆健康雷达图（多维度可视化） | ✅ |
| `SkillEventList.tsx` | 组件 | 技能演进事件列表 | ✅ |

## 依赖

- `@/services/statistics` — GrowthDashboardData、SkillTrendSeries DTO
- `@/components/features/memory/MemoryKnowledgeGraph` — 知识图谱（lazy loaded）
- `@/lib/api` — apiRequest、showApiError（PatternDigestPanel 直接调用 guardian API）
- `@/components/primitives/*` — Card、Tabs、Button
- `@/lib/utils/classnameUtils` — cn()
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
