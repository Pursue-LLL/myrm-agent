---
name: task-to-reusable-skill
description: >-
  Turnkey flywheel skill for distilling completed, successful multi-turn conversation transcripts and ad-hoc task executions
  into parameterized, production-ready reusable Skills (`SKILL.md`) and optional scheduled Cron blueprints.
  Extracts dynamic parameters, prunes redundant exploratory turns, formats contract steps with explicit validation methods,
  and persists the resulting skill into the workspace or prebuilt asset catalog.
version: 1.0.0
category: workflow-orchestration
tags:
  - task-flywheel
  - transcript-to-skill
  - skill-synthesis
  - parameter-extraction
  - cron-blueprint
  - 任务转技能
  - 飞轮沉淀
  - 可复用技能
license: MIT
allowed-tools: file_read_tool file_write_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Successful Turn Isolation & Parameterization — isolate the winning path from the current or targeted transcript and parameterize static inputs (e.g., dates, URLs, file paths)"
    - "Phase 2: Minimal Toolchain & Contract Distillation — prune trial-and-error noise, identify essential tools, and formulate contract steps with deterministic verification methods"
    - "Phase 3: Standard SKILL.md Compilation & Quality Gate — generate compliant YAML frontmatter, execution SOP, potential traps, and acceptance checklists"
    - "Phase 4: Workspace Registration & Cron Blueprint Linkage — write SKILL.md to workspace or assets, and optionally emit a cron blueprint configuration for automated recurring execution"
  potential_traps:
    - description: "Hardcoding dynamic runtime values (specific dates, temporary filenames, user IDs) into the synthesized skill"
      mitigation: "Strictly identify and convert dynamic variables into parameterized placeholders (e.g., {{TARGET_DATE}}, {{FILE_PATH}})"
      severity: critical
    - description: "Including noisy trial-and-error failed tool loops in the resulting skill SOP"
      mitigation: "Filter only the successful, golden execution path during Phase 2 distillation"
      severity: high
    - description: "Synthesizing skills without verifiable exit gates and potential traps"
      mitigation: "Mandate at least two verification steps and two potential traps in the generated YAML frontmatter contract"
      severity: high
  verification_steps:
    - step_id: parameter_placeholders_verified
      description: "Ensure dynamic runtime variables are parameterized into standard template placeholders"
      validation_method: "Inspect output SKILL.md for template placeholders or input variable declarations"
      is_required: true
    - step_id: skill_contract_compliant
      description: "Verify that the generated SKILL.md satisfies standard Myrm skill contract schema"
      validation_method: "Check for name, description, allowed-tools, and contract sections in frontmatter"
      is_required: true
  success_criteria: "An ad-hoc successful task run is crystallized into an unambiguous, reusable SKILL.md with clear SOP, minimal toolchain, and optional cron blueprint integration."
  estimated_duration_seconds: 300
---

# Task Transcript to Reusable Skill Flywheel

The `task-to-reusable-skill` skill closes the loop between one-off problem solving and institutionalized automation. It turns any successfully completed multi-turn task conversation into a hardened, repeatable, and shareable skill package.

---

## 1. The 4-Phase Flywheel Pipeline

```
[一次性成功执行的任务会话 (Successful Task Transcript)]
                           ↓
[Phase 1: 黄金路径提炼与动态入参参数化 (Parameterization & Winning Path)]
                           ↓
[Phase 2: 去噪蒸馏与最小工具链契约提炼 (Pruning & Minimal Toolchain Contract)]
                           ↓
[Phase 3: 标准化 SKILL.md 编译与质量门禁 (Frontmatter, SOP & Gate Assembly)]
                           ↓
[Phase 4: 空间持久化与 Cron 定时蓝图联动 (Persistence & Cron Blueprint Binding)]
```

---

## 2. Standard Execution SOP

### Phase 1: Winning Path Extraction & Parameterization
1. Identify the core user intent and the successful terminal response.
2. Backtrack through tool execution turns, discarding dead ends, syntax errors, and retries.
3. Detect static literal values that should be user-supplied parameters:
   - Dates/Timestamps (`2026-09-09` ➔ `{{TARGET_DATE}}`)
   - Resource URLs (`https://...` ➔ `{{TARGET_URL}}`)
   - Report Scopes or Queries (`last week marketing metrics` ➔ `{{METRIC_SCOPE}}`)

### Phase 2: Toolchain & Contract Synthesis
1. List the minimal set of tools strictly required to execute the winning path.
2. Formulate sequential execution phases (Ingestion ➔ Processing ➔ Output).
3. Extract potential failure traps based on errors encountered during the original run:
   - For every retry or error that occurred in the session, document it under `potential_traps` with its mitigation.

### Phase 3: Standard SKILL.md Assembly
Compile the skill into standard markdown format with YAML frontmatter:

```markdown
---
name: distilled-<task-slug>
description: >-
  Automated skill for <task objective>.
version: 1.0.0
category: automation
tags:
  - distilled-skill
  - <tag-1>
allowed-tools: <tool-1> <tool-2>
contract:
  steps:
    - "Phase 1: <Action>"
    - "Phase 2: <Action>"
  potential_traps:
    - description: "<Failure mode>"
      mitigation: "<How to avoid>"
      severity: high
  verification_steps:
    - step_id: output_verified
      description: "Verify generated artifact exists and is non-empty"
      validation_method: "Check file existence and content length"
      is_required: true
  success_criteria: "<Clear acceptance state>"
  estimated_duration_seconds: 180
---

# <Skill Title>

## Overview
...
## Execution SOP
...
```

### Phase 4: Persistence & Cron Blueprint Linkage
1. Persist the file to `assets/prebuilt_skills/<skill-name>/SKILL.md` or workspace `.skills/<skill-name>/SKILL.md`.
2. If the user indicates recurrence (e.g. "Run this weekly every Friday at 18:00"), emit a matching **Cron Blueprint**:

```json
{
  "name": "Weekly Execution: {{SKILL_NAME}}",
  "schedule": "0 18 * * 5",
  "skill_ids": ["{{SKILL_NAME}}"],
  "prompt_template": "Execute {{SKILL_NAME}} with scope: {{DEFAULT_SCOPE}}",
  "target_channel": "workspace_notification"
}
```

---

## 3. Quality Gate Checklist

- [ ] Are all concrete session-specific artifacts parameterized with placeholders?
- [ ] Were all failed exploration paths and error traces removed from the SOP?
- [ ] Does frontmatter contain valid `contract` with at least 2 steps, traps, and verification items?
- [ ] Is the generated file ready for immediate execution without manual code editing?
