---
name: task-transcript-to-skill
description: >-
  Extract, crystallize, and mint reusable enterprise-grade Skill packages (SKILL.md)
  and Cron Blueprints from successful multi-turn execution transcripts and conversation
  histories. Prunes trial-and-error noise, abstracts hardcoded values into typed parameters,
  embeds Human-in-the-Loop pause gates, and pairs with recurring scheduled tasks.
version: 1.0.0
category: automation
tags:
  - transcript-to-skill
  - flywheel
  - distillation
  - cron-blueprint
  - skill-generator
  - hitl-gate
  - 会话转技能
  - 飞轮沉淀
  - 定时蓝图
allowed-tools: file_read_tool file_write_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Task Success Verification & Physical Artifact Audit — Verify that the prior conversation concluded with verified, tangible deliverables"
    - "Phase 2: Trajectory De-Noising & Logic Distillation — Prune retry thrashing and dead ends; extract pure Directed Acyclic Graph (DAG) of actions"
    - "Phase 3: Parameter Generalization & Frontmatter Synthesis — Convert hardcoded paths/names into variables; generate valid YAML frontmatter"
    - "Phase 4: Cron Blueprint Pairing & One-Click Minting — Package the skill alongside a recurring Cron blueprint definition for automated execution"
  potential_traps:
    - description: "Crystallizing failed or partial conversational attempts into permanent skills"
      mitigation: "Strict gate: never mint a skill unless the source session ended with a verified success state"
      severity: critical
    - description: "Retaining specific hardcoded file paths (e.g. /tmp/demo_user_123.csv) inside distilled skill instructions"
      mitigation: "Enforce semantic parameter replacement: replace literal paths with generic placeholders or input variables"
      severity: high
    - description: "Missing Human-in-the-Loop review points in sensitive external operations"
      mitigation: "Automatically inject ask_question_tool or explicit confirmation pauses before irreversible side-effects"
      severity: high
  verification_steps:
    - step_id: skill_frontmatter_valid
      description: "Verify that synthesized SKILL.md adheres to valid YAML frontmatter and character limits"
      validation_method: "Inspect YAML syntax, contract fields, and length constraints"
      is_required: true
    - step_id: parameter_generalization_checked
      description: "Ensure no ephemeral session IDs or temporary absolute paths leak into the final skill"
      validation_method: "Grep output for UUIDs, /tmp/ markers, or user-specific paths"
      is_required: true
  success_criteria: "A one-click reproducible SKILL.md and optional Cron blueprint are produced from conversation history without manual prompt engineering."
  estimated_duration_seconds: 240
---

# One-Click Task Transcript to Reusable Skill Flywheel

## Overview

A major bottleneck in agent productivity is the "one-off success amnesia": a user or engineer spends 20 minutes guiding an agent through a complex workflow (e.g. weekly financial reconciliation, scraping competitors, or building a PDF brief), but the resulting knowledge remains locked inside that single chat thread. Next week, the user must start from scratch.

The **Task Transcript to Reusable Skill Flywheel** converts ad-hoc execution traces into reusable, team-shareable, and automatable assets:
1. **Denoised SOP Specification**: Strips intermediate debugging attempts and dead ends.
2. **Standardized `SKILL.md`**: Generates production-ready metadata, parameter schemas, and negative guardrails.
3. **Scheduled Cron Blueprint**: Links the distilled skill to recurring automated executions (e.g. run every Monday at 9:00 AM).

---

## The 4-Phase Distillation Pipeline

### Phase 1: Physical Verification Gate
Before initiating distillation, the agent must check:
- Did the source conversation achieve its core goal?
- Were output files physically created, verified, and non-empty?
- If the task failed or aborted, distillation is rejected immediately.

### Phase 2: Trajectory De-Noising & Flow Mining
1. Filter out:
   - Tool execution errors and their immediate recovery loops.
   - Conversational pleasantries, small talk, and unrelated tangents.
   - Redundant duplicate reads.
2. Formulate the core sequential flow:
   - Input ingestion $\rightarrow$ Processing & Transformation $\rightarrow$ Quality Gate Verification $\rightarrow$ Deliverable Packaging.

### Phase 3: Variable Generalization & Frontmatter Generation
Transform instance-specific inputs into configurable variables:
- `user_20260908.xlsx` $\rightarrow$ `[Target Spreadsheet / Path]`
- `report_v3_final.docx` $\rightarrow$ `[Output Document Target]`
- Inject **Human-in-the-Loop (HITL) Pause Gates** whenever destructive tools or external email/webhook operations occur.

### Phase 4: Cron Blueprint Pairing
Produce the final artifacts:
1. `skills/{skill-name}/SKILL.md`
2. Optional `CronBlueprint` JSON/YAML snippet:
```yaml
id: recurring_{skill_name}
name: "Scheduled {Skill Name} Runner"
schedule: "0 9 * * 1"  # Every Monday at 9am
skill_ids:
  - "{skill_name}"
prompt: "Execute weekly run adhering to the {skill_name} standard operating procedure."
```

---

## Output Quality Gate

- [ ] All frontmatter fields (`name`, `description`, `version`, `category`, `contract`) strictly populated.
- [ ] No hardcoded personal tokens, local file paths, or private emails retained.
- [ ] Negative constraints and verification criteria explicitly declared.
