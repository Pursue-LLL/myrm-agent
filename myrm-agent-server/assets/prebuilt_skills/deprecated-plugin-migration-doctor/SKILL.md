---
name: deprecated-plugin-migration-doctor
description: >-
  Automated diagnostic and migration engine for deprecated plugin/skill syntax, Breaking Changes,
  and legacy configuration structures. Inspired by openclaw doctor --fix and modern linter-fixers,
  it inspects manifests, yaml configs, and SKILL.md files, detects deprecated keys (e.g. tools vs
  allowed-tools, on_agent_init vs on_session_start, legacy env arrays), generates deterministic AST/YAML
  diffs, and performs safe, atomic migrations with automatic backup and rollback guarantees.
version: 1.0.0
category: developer-tools
tags:
  - doctor-fix
  - syntax-migration
  - breaking-changes
  - linter-autofix
  - backwards-compatibility
  - skill-migration
  - plugin-modernization
  - 语法迁移
  - 自动化修复
  - 弃用诊断
license: MIT
allowed-tools: file_write_tool file_read_tool file_edit_tool bash_code_execute_tool
contract:
  steps:
    - 1. Scan target skill/plugin workspace for deprecated configuration files and obsolete schema markers
    - 2. Compute migration diff report classifying issues into warnings, breaking deprecations, and auto-fixable rules
    - 3. Create atomic backup snapshot (.doctor_backup/timestamp) before modifying any disk files
    - 4. Apply deterministic rewrite transformations (YAML AST/string replacement) for all approved fix rules
    - 5. Run post-migration validation test suite to ensure schema conformity and operational health
  potential_traps:
    - description: In-place file modification without creating atomic rollback backups
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Aggressive syntax rewriting that destroys user-defined inline YAML comments or custom metadata
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Misinterpreting proprietary vendor extensions as standard deprecated fields
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Applying fixes while concurrent agent sessions are actively executing against the target skill
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - step_id: verify_1
      description: Verify backup snapshot directory is successfully created and populated before any file writes
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_2
      description: Ensure all transformed files parse as valid YAML/Markdown with zero syntax errors
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_3
      description: Validate that migrated skill passes agentskills.io schema conformance checks
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
  success_criteria: '100% resolution of target deprecated syntax patterns with zero loss of comments and custom logic; Zero regression in skill functionality confirmed by post-migration verification gate'
---

# Deprecated Plugin Syntax Migration & Doctor Auto-Fix Engine

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


As the Agent and Skill ecosystem evolves rapidly across versions (e.g. OpenClaw, Hermes, LangChain, and Myrm),
breaking syntax changes frequently break legacy skills: obsolete manifest names (`plugin.yaml` vs `SKILL.md`),
renamed permission arrays (`tools` vs `allowed-tools`), legacy lifecycle hooks, and outdated environment declarations.

The `deprecated-plugin-migration-doctor` skill acts as an automated **Diagnostic Doctor & Safe Auto-Fixer**
(equivalent to `openclaw doctor --fix`), diagnosing obsolete syntax patterns, presenting precise visual diffs,
and executing non-destructive, atomic migrations with guaranteed rollbacks.

---

## 1. The 4-Phase Migration & Doctor Pipeline

```
┌────────────────────────────────────────────────────────────────────────┐
│             Deprecated Plugin Migration & Doctor Architecture          │
├───────────────────────────────────┬────────────────────────────────────┤
│ Phase 1: Lint & Deprecation Probe │ Phase 2: Diff & Impact Analysis    │
│ - Scan manifests & SKILL.md       │ - Classify Breaking vs Warnings    │
│ - Match AST/Regex rule registry   │ - Generate Unified Patch Preview   │
├───────────────────────────────────┼────────────────────────────────────┤
│ Phase 3: Atomic Backup & Fix      │ Phase 4: Validation & Rollback Gate│
│ - Create .doctor_backup/ snapshot │ - Validate YAML & Contract Schema  │
│ - Apply comment-preserving writes │ - Auto-revert if tests fail        │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 2. Deprecation Rule Registry & Canonical Transformations

| Deprecated Pattern | Modern Standard (SSOT) | Transformation Logic | Severity |
|---|---|---|---|
| `plugin.yaml` / `manifest.json` | `SKILL.md` (YAML Frontmatter) | Consolidate manifest fields into Markdown header block | **CRITICAL** |
| `tools: "bash, file_read"` | `allowed-tools: [bash_code_execute_tool, file_read_tool]` | Split comma string, map to canonical tool names, format as YAML list | **HIGH** |
| `on_agent_init: run.py` | `hooks: { on_session_start: run.py }` | Map legacy single hook to nested hook event table | **MEDIUM** |
| `env: [VAR1, VAR2]` | `required_env_vars: [VAR1, VAR2]` | Rename property key, preserve variable names | **MEDIUM** |
| Missing `contract.steps` | Scaffolded `contract.steps: ["Step 1..."]` | Inject standard contract template satisfying schema gate | **HIGH** |

---

## 3. Operational Safety & Atomic Rollback Protocol

Before applying any change to a user's skills or plugins:

1. **Pre-flight Lock**: Verify target files are not currently locked or being executed.
2. **Atomic Snapshot**:
   ```bash
   mkdir -p .doctor_backup/$(date +%Y%m%d_%H%M%S)
   cp -rp <target_skill_dir> .doctor_backup/$(date +%Y%m%d_%H%M%S)/
   ```
3. **Comment-Preserving Rewriter**: Ensure AST or selective regex replacements preserve YAML formatting and comments.
4. **Post-Fix Conformance Gate**: If syntax validation fails, immediately restore from snapshot:
   ```bash
   cp -rp .doctor_backup/<timestamp>/* <target_skill_dir>/
   ```
