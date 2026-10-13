# api/statistics/skill_growth/

## 架构概述

成长看板的技能侧数据域：技能进化时间线、逐技能用量/结果趋势、7 天健康判定。只读聚合 Curator 的 `.stats.json` 账本与技能成长服务，不写任何存储。健康分由 Harness `SkillHealthEvaluator` 按「已观测结果」计算；观测结果少于 Curator 的最小门槛（`min_call_count_for_quality_check`）时状态为 `UNPROVEN`，不显示成功率。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出响应模型与三个只读 fetcher，供 `growth_dashboard.py` 使用 | ✅ |
| `models.py` | 契约 | `SkillEvolutionEvent` / `SkillTrendPoint` / `SkillTrendSeries` / `SkillHealthItem` 响应模型（含 `observed_count*` 与 `min_observed_count` 证据字段） | ✅ |
| `ledger.py` | 模块 | `iter_skill_ledgers`：遍历本地技能目录并读取各自用量账本，趋势与健康共用的唯一读取路径；只读已有账本，无账本目录（含其他工具拥有的技能根）跳过，面板读取不在其中创建文件 | ✅ |
| `evolution.py` | 模块 | 技能总数、进化计数与最近进化事件快照 | ✅ |
| `trends.py` | 模块 | 逐技能按日聚合用量与已观测成功率（无观测结果的日子不给成功率） | ✅ |
| `health.py` | 模块 | 7 天窗口健康判定：只评估窗口内有运行的技能（沉睡与归档由 Curator 生命周期决定，技能库已展示）；成功/失败只计已观测结果，比率与质量状态需达到 Curator 最小观测门槛 | ✅ |
