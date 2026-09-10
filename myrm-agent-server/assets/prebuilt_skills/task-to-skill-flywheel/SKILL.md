---
name: task-to-skill-flywheel
description: "Transform completed task session transcripts and multi-turn workflows into self-contained, parametric, and reusable Skill Packs with frontmatter, allowed tools, and SOP contracts."
version: "1.0.0"
category: "operations"
tags:
  - task-to-skill
  - flywheel
  - workflow-capture
  - automation
  - self-improvement
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# One-Click Task Transcript to Reusable Skill Flywheel (任务会话一键固化为复用技能飞轮)

## Overview

A dedicated flywheel skill that converts a successful, complex multi-turn conversation into a permanent, reusable, and parameter-driven **Production Skill Pack (`.myrm/skills/{skill_slug}/SKILL.md`)**.

Instead of manually re-typing multi-step prompts or copy-pasting instructions, this skill distills the conversation's essence into a reproducible SOP that any agent or Cron scheduler can invoke with fresh arguments.

---

## 4-Stage Flywheel Synthesis Pipeline (四阶技能萃取流水线)

```
[Stage 1: Session Trace Ingestion (会话轨迹摄取)]
  - Analyze user intent, intermediate tool invocations, inputs, and final artifacts
  - Filter out temporary mistakes, rejected tool calls, and conversational fluff
         ↓
[Stage 2: Parametric Slot Abstraction (参数抽象与槽位泛化)]
  - Convert hardcoded inputs (e.g. "2026-09-08", "Project Alpha", "user@corp.com")
  - Extract dynamic variables: `{{target_date}}`, `{{project_name}}`, `{{recipient_email}}`
  - Define input parameter schema (types, defaults, required flags)
         ↓
[Stage 3: Standard Skill Contract Authoring (标准技能规约生成)]
  - Generate YAML frontmatter with strictly scoped `allowed-tools`
  - Structure an actionable SOP: Overview -> Inputs -> Step-by-Step Execution -> Quality Gate
  - Include deterministic negative constraints and anti-hallucination rules
         ↓
[Stage 4: Workspace Registration & Flywheel Linking (工作区挂载与飞轮联动)]
  - Write bundle directly to `.myrm/skills/{skill_slug}/SKILL.md`
  - Expose instant command CTA or optional Cron trigger blueprint binding
```

---

## Output Contract & Template (`.myrm/skills/{skill_slug}/SKILL.md`)

```markdown
---
name: {skill_slug}
description: "{Extracted clear description of the automated workflow}"
version: "1.0.0"
category: "productivity"
tags:
  - user-crystallized
  - automated-workflow
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# {Human Readable Skill Title}

## Overview
{Clear 2-sentence explanation of what this workflow accomplishes}

## Input Parameters
- `{{primary_param}}`: (string, required) Description of parameter.
- `{{optional_param}}`: (number, optional, default: 10) Description.

## Standard Execution SOP
1. **Step 1: Input Validation**: Check prerequisites and confirm target paths exist.
2. **Step 2: Processing Core**: Execute the core logic using specified tools.
3. **Step 3: Verification & Output**: Verify artifact integrity and present summary.

## Quality Gate & Negative Constraints
- Never execute destructive mutations without explicit parameter authorization.
- Always output deterministic verification logs upon completion.
```

---

## Operational Safeguards
- **Anti-Hardcoding**: Ensure no ephemeral session-specific tokens, personal phone numbers, or local absolute machine paths leak into the synthesized template.
- **Minimal Tool Exposure**: Only grant the specific tools actually utilized in the successful trace; never assign broad wildcard permissions.
