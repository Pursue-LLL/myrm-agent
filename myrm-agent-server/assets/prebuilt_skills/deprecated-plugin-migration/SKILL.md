---
name: deprecated-plugin-migration
description: >-
  Audits, translates, and auto-repairs legacy or deprecated plugin and skill syntax
  (OpenClaw legacy plugins, deprecated SKILL.md schema v0, old YAML frontmatter keys)
  into standard Agentskills.io contracts. Integrates with `myrm doctor --fix` CLI to
  perform non-destructive in-place upgrades with automated backup and diff preview.
version: 1.0.0
category: maintenance-engineering
tags:
  - plugin-migration
  - doctor-fix
  - syntax-upgrade
  - deprecation-repair
  - backward-compatibility
  - 语法迁移
  - 自动修复
  - 插件自愈
allowed-tools: file_read_tool file_write_tool file_edit_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Deprecation Scanning — scan target skill/plugin folders for obsolete keys (`tools:`, `commands:`, `action:`, legacy XML envelopes)"
    - "Phase 2: In-Memory AST & Schema Migration — map legacy structure to modern Agentskills.io frontmatter (allowed-tools, contract, verification_steps)"
    - "Phase 3: Diff Generation & Safety Backup — create `.bak` snapshot and render a unified diff showing planned modifications"
    - "Phase 4: Atomic In-Place Patching & Doctor Verification — write upgraded file and run `myrm doctor` to verify zero regression"
  potential_traps:
    - description: "Overwriting custom logic or user comments during automated YAML serialization"
      mitigation: "Use comment-preserving YAML parser (ruamel.yaml) or targeted regex AST replacement"
      severity: high
    - description: "Migrating active skills without creating recovery backups"
      mitigation: "Strict requirement to generate `.bak.{timestamp}` prior to any disk write"
      severity: high
  verification_steps:
    - step_id: backup_verified
      description: "Ensure backup file exists on disk before applying modifications"
      validation_method: "Verify `{file}.bak` exists and matches original checksum"
      is_required: true
    - step_id: doctor_check_clean
      description: "Ensure migrated skill passes all validation checks"
      validation_method: "Run doctor diagnostic and confirm 0 deprecation warnings"
      is_required: true
  success_criteria: "Legacy plugin files are upgraded to current specification with full backup safety and zero diagnostic errors"
  estimated_duration_seconds: 300
---

# Deprecated Plugin Syntax Migration & Doctor Auto-Fix

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

As agent ecosystems evolve, plugin and skill syntaxes undergo breaking schema migrations (e.g. moving from freeform `tools:` strings to structured `allowed-tools`, deprecated `env_vars` blocks, or obsolete OpenClaw plugin JSON manifests). Manually rewriting dozens of skill files is tedious and prone to syntax errors.

The `deprecated-plugin-migration` skill provides automated, non-destructive migration and pairs with `myrm doctor --fix` to heal legacy assets in place.

## Deprecation Mapping Rules

| Legacy Schema / Key | Target Modern Standard | Migration Transform |
| --- | --- | --- |
| `tools: [bash, edit]` | `allowed-tools: bash_code_execute_tool file_edit_tool` | Map shorthand names to canonical tool identifiers |
| `requires.tools: [...]` | `requires_tools: [...]` | Flatten nested requires keys to top-level frontmatter |
| `action_space: [...]` | `allowed-tools: ...` | Standardize action space terminology to Agentskills spec |
| `prompt_template:` | Markdown Body `# SOP` | Extract embedded prompt strings into clean markdown text |

## The 4-Phase Auto-Fix Pipeline

```
Legacy Plugin / SKILL.md
           │
           ▼
Phase 1: Deprecation Rule Scanner (Detect Obsolete Patterns)
           │
           ▼
Phase 2: In-Memory AST Transformation & Diff Generation
           │
           ▼
Phase 3: Snapshot Creation (`{path}.bak.{timestamp}`)
           │
           ▼
Phase 4: In-Place Atomic Write & Doctor Diagnostic Pass
```

## Standard Execution SOP

1. **Scan Target Directory**: Identify all `.md` and `.yaml` skill definitions with deprecated syntax.
2. **Generate Safety Snapshot**: Create `.bak` copies before any disk modification.
3. **Apply Modernization Rules**: Transform legacy keys, map canonical tool names, and format YAML frontmatter.
4. **Run Doctor Verification**: Execute doctor diagnostics to verify that all upgraded skills parse cleanly without warnings.
