---
name: todo-dailylog-weeklyreport-loop
description: "End-to-end closed-loop productivity workflow connecting Morning Todo Planning, Daily Kanban Task Tracking, Evening Reconciliation Log, and Automated Friday Executive Weekly Reporting."
version: "1.0.0"
category: "productivity"
tags:
  - todo
  - daily-log
  - weekly-report
  - closed-loop
  - kanban
  - productivity
  - work-rhythm
allowed-tools:
  - kanban_show
  - kanban_add_task
  - kanban_list_tasks
  - memory_save_tool
  - memory_search_tool
  - file_write_tool
  - file_read_tool
---

# Personal Todo, Daily Log & Weekly Report Closed Loop (待办-对账-周报闭环生产力特征包)

## Overview

This skill establishes a closed-loop productivity rhythm that connects:
1. **Morning Planning (晨间定焦)**: Pulls yesterday's unfinished tasks and strategic goals into today's Top 3-5 focus items on the Kanban board.
2. **Daytime Execution (日间核销)**: Moves cards through `todo` -> `in_progress` -> `done` with associated artifact and commit verification links.
3. **Evening Reconciliation (晚间对账)**: Audits planned vs actual outcomes, captures learnings and blockers, and generates a persistent Daily Log.
4. **Friday Executive Synthesis (周末周报)**: Aggregates Monday-Friday logs into an executive-ready weekly summary following the Pyramid Principle.

---

## The 4-Phase Operating Rhythm

```
┌──────────────────────────────────────────────────────────────┐
│ Phase 1: Morning Focus (晨间定焦 · 08:30)                    │
│ • Review active Kanban board via kanban_show          │
│ • Select 3 core MUST-WIN tasks for the day                   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 2: Execution & Proof (日间执行 · 09:00 - 18:00)         │
│ • Atomic status updates on Kanban cards                      │
│ • Attach physical evidence (file path, PR link, test pass)   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 3: Evening Reconciliation (晚间对账 · 18:30)           │
│ • Audit completed vs rollover tasks                          │
│ • Generate Daily Log: `daily-logs/YYYY-MM-DD.md`             │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 4: Friday Weekly Synthesis (周末周报 · 周五 17:00)      │
│ • Harvest 5 daily logs + archived Kanban cards               │
│ • Synthesize Pyramid Weekly Report: `weekly/YYYY-Www.md`     │
└──────────────────────────────────────────────────────────────┘
```

---

## 1. Daily Log Format Specification (`daily-logs/YYYY-MM-DD.md`)

```markdown
# 工作日志 (Daily Work Log) · 2026-09-10

## 1. 今日焦点对账 (Focus Reconciliation)
- [x] **[P0] 完成 Topic 08 条目 #16 待办-日志-周报闭环交付**
  - 产出凭证: `assets/prebuilt_skills/todo-dailylog-weeklyreport-loop/SKILL.md`
  - 验证结果: 单测与架构测试 100% 通过
- [x] **[P1] 编写架构守卫测试**
  - 产出凭证: `tests/architecture/test_prebuilt_skill_todo_dailylog_weeklyreport_loop.py`
- [ ] **[P2] 晚间代码清理与归档**
  - 顺延原因: 优先级让位于线上紧急构建发布，顺延至明天首项

## 2. 关键产出与证据链 (Artifacts & Evidence)
- PR / 提交: `git commit -m "feat(skills): add todo-dailylog-weeklyreport-loop"`
- 核心物料: 交付特征包技能规范与单元测试

## 3. 阻塞与卡点 (Blockers & Risks)
- 无阻断项。

## 4. 明日计划 (Tomorrow's Forecast)
- 启动 Topic 08 条目 #17 EditablePptxQuickGenerateFeaturedPackEmptyChatPromptTemplate
```

---

## 2. Weekly Report Synthesis Specification (`weekly/YYYY-Www.md`)

When synthesizing weekly reports on Friday, enforce the **Pyramid Principle (结论先行、以上统下、MECE 分类)**:

```markdown
# 周报 (Executive Weekly Report) · 2026-W37 (09-07 ~ 09-11)

## 一、本周核心战果概览 (Executive Summary)
本周聚焦技能工具链与工件系统深度落地，共完成 6 项核心能力交付，测试通过率 100%，无线上阻断故障。

## 二、重点项目交付详情 (Deliverables & Metrics)
### 1. 技能体系与研发提效
- **企业品牌 Office 技能与同事交接**: 制定统一母版规范，抹平跨部门排版成本。
- **人设语料蒸馏对话型技能**: 实现专家语料一键打包与高保真对话。
- **WB 20 大技能迁移映射包**: 完成 20 项核心场景 1:1 精确映射与增强说明。

## 三、关键指标异动与复盘 (Key Metrics & Learnings)
- 交付吞吐: 6 项 P1/P0 特征落地，交付周期缩短 35%。
- 踩坑沉淀: 强化了技能经验库读前写后自进化循环机制。

## 四、下周核心计划 (Next Week Priorities)
1. [P0] 完成 Topic 08 条目 #17 ~ #20 全部收尾与生产环境验收。
2. [P1] 展开与控制平面多沙箱协同联调。
```
