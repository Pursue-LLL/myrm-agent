---
name: transcript-to-skill-flywheel
description: >-
  Turn completed, multi-turn conversational task executions and complex tool workflows into
  reusable, parameter-driven Agent Skills and automated Cron jobs. Abstracts specific entity
  values into configuration variables, drafts agentskills.io compliant SKILL.md packages,
  and establishes an ongoing task-to-automation flywheel.
version: 1.0.0
category: productivity
tags:
  - transcript-to-skill
  - task-flywheel
  - automation
  - skill-synthesis
  - cron-automation
  - 会话转技能
  - 任务沉淀飞轮
  - 自动化提炼
allowed-tools: file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Transcript Analysis & Milestone Distillation — parse recent turns to isolate problem, tool calls, and successful deliverables"
    - "Phase 2: Variable Parameterization & Boundary Isolation — replace specific names, dates, and hardcoded IDs with templated variables"
    - "Phase 3: Standardized SKILL.md Packaging — compile frontmatter, contract, execution SOP, and verification rules"
    - "Phase 4: Cron Job Automation Linking — configure optional scheduled cron blueprint for recurring autonomous runs"
  potential_traps:
    - description: "Hardcoding ephemeral user data or specific file paths directly into the generated skill"
      mitigation: "Strict parameterization scan to ensure dynamic inputs use placeholders like {{target_url}} or {{report_date}}"
      severity: high
    - description: "Creating a bloated skill that repeats trivial conversational small talk"
      mitigation: "Extract only core tool orchestration and deterministic steps into the SOP"
      severity: medium
  verification_steps:
    - step_id: skill_frontmatter_valid
      description: "Ensure generated skill contains valid YAML frontmatter with name, description, and allowed-tools"
      validation_method: "Parse frontmatter against agentskills.io spec"
      is_required: true
    - step_id: parameter_placeholders_verified
      description: "Ensure all entity-specific parameters are properly abstracted"
      validation_method: "Inspect SOP for absence of hardcoded personal paths or API keys"
      is_required: true
  success_criteria: "A production-grade, self-contained SKILL.md asset saved to workspace or prebuilt skills, ready for instant invocation or cron scheduling"
  estimated_duration_seconds: 400
---

# Transcript-to-Skill Flywheel (任务会话转可复用技能与自动化飞轮)

## Overview

When an Agent successfully solves a non-trivial user task—such as:
- *"Fetch financial filings for 3 competitors, compare gross margins in Python, and output an Excel report"*
- *"Scan recent GitHub issues, summarize user bugs, and post a standup summary"*

This execution pattern should NOT remain a one-off ephemeral chat. The **Transcript-to-Skill Flywheel** converts the successful session into a permanent, reusable **Skill Package (`SKILL.md`)** that can be triggered on demand or scheduled autonomously via Cron.

---

## The 4-Phase Flywheel Pipeline

```
[1. 会话轨迹分析与里程碑萃取]
             ↓
[2. 变量参数化与硬编码抽离 (e.g. {{company_list}}, {{report_frequency}})]
             ↓
[3. 标准 SKILL.md 规范封装 (Frontmatter + Contract + SOP)]
             ↓
[4. 自动化 Cron 蓝图绑定与持久化保存]
```

### 1. Milestone & Tool Extraction
Identify:
- Which tools were invoked in what order? (e.g. `web_search` ➔ `bash_code_execute` ➔ `file_write`)
- What specific edge cases were encountered and resolved during the conversation?

### 2. Variable Parameterization
Replace hardcoded data with generic parameters:
- `2026-Q2-Nvidia-Report.pdf` ➔ `{{input_document}}`
- `tesla, rivian, lucid` ➔ `{{target_competitors}}`
- `my-slack-webhook-url` ➔ `{{notification_webhook}}`

### 3. Template Synthesis
Generate a clean, self-contained `SKILL.md` under `assets/prebuilt_skills/` or user's custom skill store.

### 4. Cron Automation Linkage
If the task is recurring (e.g. daily, weekly, monthly), suggest a matching Cron job definition:
```json
{
  "name": "Weekly Competitor Financial Sync",
  "cron_expression": "0 9 * * 1",
  "skill_ids": ["{{generated_skill_id}}"],
  "prompt": "Run weekly competitor margin analysis using {{generated_skill_id}}"
}
```
