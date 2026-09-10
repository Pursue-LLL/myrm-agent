---
name: personal-todo-daily-weekly-loop
description: "End-to-end closed-loop productivity workflow linking granular task tracking (Todo/Kanban), end-of-day journal reconciliation (Daily Log), and automated structured weekly reporting (Weekly Report)."
version: "1.0.0"
category: "productivity"
tags:
  - todo
  - kanban
  - daily-log
  - journal
  - weekly-report
  - productivity-loop
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Personal Todo, Daily Log & Weekly Report Closed Loop (个人待办-对账-周报闭环管理技能)

## Overview

A dedicated skill for maintaining a continuous, zero-loss productivity lifecycle that seamlessly connects:
1. **Granular Todo Tracking**: Capturing actionable work items with priorities, estimates, and status.
2. **End-of-Day Journal Reconciliation**: Reflecting on completed items, recording blockers, and capturing daily learnings.
3. **Automated Weekly Report Synthesis**: Aggregating 5 days of journal data into an executive-ready, audit-grade weekly progress report.

---

## 3-Phase Continuous Lifecycle (三阶段闭环生命周期)

```
[Phase 1: Dynamic Task Tracking (待办登记与流转)]
  - Capture tasks into workspace todos (`.myrm/progress/todos.json` via todo_write)
  - Prioritize tasks via Eisenhower quadrant (Urgent/Important)
  - Maintain atomic statuses: pending -> in_progress -> completed / blocked / cancelled
         ↓
[Phase 2: End-of-Day Reconciliation (日终日志对账)]
  - Check off completed items against the active todo list
  - Record unexpected traps, technical debts, or stalled blockers
  - Append structured daily journal entry under `docs/journal/YYYY-MM-DD.md`
         ↓
[Phase 3: Automated Weekly Synthesis (周末周报自动归纳)]
  - Read all 5 daily log entries for the week (Monday through Friday)
  - Extract tangible deliverables, quantitative metric changes, and key blockers solved
  - Generate structured weekly report under `docs/reports/weekly-YYYY-WW.md`
```

---

## Data Contracts & Templates

### 1. Daily Journal Entry (`docs/journal/YYYY-MM-DD.md`)

```markdown
# 日志对账: YYYY-MM-DD

## 1. 今日完成事项 (Done)
- [x] [任务ID/名称]: 完成核心交付物与测试验证 (关联产物: `path/to/artifact`)
- [x] [任务ID/名称]: 修复边界条件缺陷，提交自动化验证用例

## 2. 阻塞与延期事项 (Blocked / Carried Over)
- [ ] [任务ID/名称]: 受阻于外部依赖审批，明日继续跟进

## 3. 今日技术心得与经验沉淀 (Learnings)
- 根因排查: 发现某配置项未生效的原因是默认值被覆盖，已更新不变量守卫。
```

### 2. Executive Weekly Report (`docs/reports/weekly-YYYY-WW.md`)

```markdown
# 个人工作周报 (Week WW, YYYY)

## 一、本周核心工作总结 (Executive Summary)
- 本周主要聚焦于 [核心业务目标]，重点交付了 [关键产物 1] 与 [关键产物 2]。
- 任务计划完成率: **XX%** (计划 X 项，实际完成 Y 项)。

## 二、重点交付物与实测成果 (Key Deliverables)
| 交付物名称 | 交付类型 | 成果说明与验证指标 | 状态 |
|---|---|---|---|
| [产物 A] | 代码/文档/配置 | 通过自动化测试验证，延时降低 XX% | 已完工 |
| [产物 B] | 架构方案/报告 | 完成评审并归档入库 | 已完工 |

## 三、重大问题攻关与经验沉淀 (Key Blockers & Learnings)
- **问题**: ...
- **解决方案与防复发门禁**: ...

## 四、下周重点工作计划 (Next Week Plan)
1. [优先级 P0]: 推进 ...
2. [优先级 P1]: 启动 ...
```

---

## Operational Safeguards
- **Evidence-Grounded**: Weekly summaries must reference concrete daily journal entries or artifacts. Do not invent unlogged achievements.
- **Fail-Safe**: If daily journals are missing, inspect git commit logs and recent workspace file modifications as fallback evidence.
