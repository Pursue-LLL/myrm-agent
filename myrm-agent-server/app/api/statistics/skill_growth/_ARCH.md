# api/statistics/skill_growth/

## 架构概述

成长看板的技能侧数据域：技能进化时间线、逐技能用量/结果趋势、7 天健康判定。只读聚合 Curator 的 `.stats.json` 账本与技能成长服务，不写任何存储。健康分由 Harness `SkillHealthEvaluator` 按「已观测结果」计算；观测结果少于 Curator 的最小门槛（`min_call_count_for_quality_check`）时状态为 `UNPROVEN`，不显示成功率。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出响应模型与三个只读 fetcher，供 `growth_dashboard.py` 使用 | ✅ |
| `models.py` | 契约 | `SkillEvolutionEvent` / `SkillTrendPoint` / `SkillTrendSeries` / `SkillHealthItem` 响应模型（含 `observed_count*` 与 `min_observed_count` 证据字段；趋势序列与健康项带 `truncated`，表示账本只保留最近一批记录、窗口内更早的运行已丢失） | ✅ |
| `ledger.py` | 模块 | `iter_skill_ledgers`：遍历本地技能目录并读取各自用量账本，趋势与健康共用的唯一读取路径；只读已有账本，无账本目录（含其他工具拥有的技能根）跳过，面板读取不在其中创建文件。`as_utc` / `parse_record_time`：两个面板共用的容错时间读取（naive 视为 UTC，单条无法解析的记录返回 `None`，只跳过该条）。`dated_outcomes`：按时间升序给出可读取时间记录的（时刻，已观测结果）。`window_is_clipped`：账本历史已满（Harness `SkillUsageStats.history_is_full`）且最早一条已晚于窗口起点，说明窗口内更早的运行被滚动丢弃，两个面板共用这一判断 | ✅ |
| `evolution.py` | 模块 | 技能总数、进化计数与最近进化事件快照 | ✅ |
| `trends.py` | 模块 | 逐技能按日聚合用量与已观测成功率（无观测结果的日子不给成功率）；窗口为看板所选范围的滚动 N 天（`fetch_skill_trends(days, tz)`，与健康、成本面板同口径），窗口内无运行的技能不出图；「日」按请求方时区的日历日划分（`tz` 默认 UTC），序列按窗口内使用次数合计降序、同数按名称升序，图表默认打开的就是其中用得最多的技能；账本回溯不到窗口起点的技能标 `truncated` | ✅ |
| `health.py` | 模块 | 7 天窗口健康判定：只评估窗口内有运行的技能（沉睡与归档由 Curator 生命周期决定，技能库已展示）；成功/失败只计已观测结果，比率与质量状态需达到 Curator 最小观测门槛；7 天内运行次数超过账本保留量的技能标 `truncated`，运行次数按下限读 | ✅ |
