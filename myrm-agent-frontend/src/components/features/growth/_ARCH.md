# growth/

## 架构概述

学习旅程统一模块（路由 `/journey`，旧 `/growth` 自动重定向）。展示记忆/技能/活跃度 KPI、智能节省摘要、活动热力图、健康雷达、知识图谱、技能使用趋势、技能演进时间线和行为模式发现复盘面板。

## 文件清单

| 文件                           | 地位 | 职责                                                                                                                                                       | I/O/P |
| ------------------------------ | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `GrowthDashboard.tsx`          | 核心 | 仪表盘主页面，含时间范围选择器(7/30/90D)、KPI 卡片、Savings 卡片、Tabs 编排（Overview / Evolution Digest / Knowledge Graph / Skill Trends / Daily Review） | ✅    |
| `SkillTrendChart.tsx`          | 组件 | 技能使用趋势图。支持技能选择、双维度切换（成功率/次数）、日粒度柱状图（日按用户本地时区划分，技能按已记录使用次数降序、首项默认选中）；成功率柱的提示带当日已观测次数；窗口随看板所选时间范围，所选技能不在新范围内时回落到用得最多的技能（始终有一枚高亮标签）；范围内无技能运行时给出范围化空态；账本只留最近一批运行、范围内更早的运行可能缺失时附一句说明（`truncated`）                                                   | ✅    |
| `ManifestPredictionsPanel.tsx` | 组件 | 变更清单与可证伪预测归因面板：展示演进前预期指标提升（方向/基准/目标/容差）与评测后实测对比归因判定（CONFIRMED/REFUTED/REGRESSION）及回滚补丁建议          | ✅    |
| `PatternDigestPanel.tsx`       | 组件 | 行为模式发现复盘面板。展示 Pattern Discovery 历史结果卡片、空状态引导、手动触发分析按钮                                                                    | ✅    |
| `ActivityHeatmap.tsx`          | 组件 | GitHub 风格的活动热力图渲染                                                                                                                                | ✅    |
| `DailyJournal.tsx`             | 组件 | 日志视图（按天展示对话摘要）                                                                                                                               | ✅    |
| `DailyWrapCard.tsx`            | 组件 | AI 日报摘要卡片（Daily Wrap），由 DailyJournal 使用                                                                                                        | ✅    |
| `HealthRadar.tsx`              | 组件 | 记忆健康雷达图（多维度可视化）                                                                                                                             | ✅    |
| `LearningTimeline.tsx`         | 组件 | 学习时间线面板：类型/时间过滤、稳定游标分页（请求序号防过期响应覆盖）、带确认的行内治理（乐观更新 + 失败回滚 + 撤销）                                     | ✅    |
| `TimelineNodeCard.tsx`         | 组件 | 时间线单节点卡片与行内编辑表单（字段 label 与控件关联）；来源对话跳转；智能体只显示名称不外露 id；程序性规则不展示重要度；治理动作经回调交给父级，仅持有编辑草稿 | ✅    |
| `useTimelineGovernance.ts`     | 辅助 | 时间线行内治理动作（保存编辑 / 删除记忆 / 归档或恢复技能）：乐观更新、失败回滚、撤销提示；重要度仅在用户拖动滑块后才提交，避免内容编辑静默改写                 | ✅    |
| `learningTimelineMeta.ts`      | 辅助 | 节点类型元数据、过滤页签，以及技能归档/固定、记忆变更类型的服务端元数据读取与排序比较                                                                       | ✅    |
| `SkillEventList.tsx`           | 组件 | 技能演进事件列表                                                                                                                                           | ✅    |
| `SkillHealthPanel.tsx`         | 组件 | 技能健康度与周复盘治理面板。支持全量/待治理/健康分类筛选、平滑展开全量资产，「管理」链接带技能名直达技能库已安装列表并预填搜索（`/settings/skills?search=`，由 `UnifiedSkillsSection` 读取），只列近 7 天有运行的技能（沉睡与归档由技能库的 Curator 徽章呈现）；展示 Harness 纯规则健康分与多语言治理建议；已观测结果不足的技能为「待验证」，只展示用量并说明还需多少次观测，不展示成功率；运行次数超过账本保留量（`truncated`）的技能，7 天次数按下限显示为 `N+`；本版本未知的状态不渲染徽章（不向用户暴露状态码）；行带 `data-testid="skill-health-row"` 供 E2E 定位 | ✅    |
| `growthMarkdownExport.ts`      | 辅助 | 成长报告 Markdown 导出：技能排名只含已判定（非「待验证」）的技能，结论以 `labels.skillStatus` 译为当前语言而非状态码，不改写入参；账本截断（`truncated`）的技能，7 天次数同样写作 `N+` | ✅    |

## 依赖

- `@/services/statistics` — GrowthDashboardData、SkillTrendSeries DTO
- `@/components/features/memory/insights/MemoryKnowledgeGraph` — 知识图谱（lazy loaded）
- `@/lib/api` — apiRequest、showApiError（PatternDigestPanel 直接调用 guardian API）
- `@/components/primitives/*` — Card、Tabs、Button
- `@/lib/utils/classnameUtils` — cn()
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
