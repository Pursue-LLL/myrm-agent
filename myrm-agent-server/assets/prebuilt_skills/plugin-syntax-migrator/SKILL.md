---
name: "plugin-syntax-migrator"
version: "1.0.0"
category: "engineering"
description: "Detects, migrates, and auto-fixes deprecated plugin, tool, and SKILL.md syntax per the latest Agentskills and Myrm specifications. Generates diff reports, creates pre-flight atomic backups, and executes doctor auto-fix workflows."
triggers:
  - "migrate deprecated plugin syntax"
  - "fix deprecated skill yaml frontmatter"
  - "myrm doctor --fix skills"
  - "audit and upgrade legacy plugin specs"
  - "plugin-syntax-migrator"
inputs:
  target_directory:
    type: "string"
    description: "Path to skills or plugins directory to scan and upgrade (defaults to workspace skills)."
    default: "assets/prebuilt_skills"
  dry_run:
    type: "boolean"
    description: "If true, only report deprecation findings and proposed diffs without applying file mutations."
    default: false
outputs:
  migration_report:
    type: "file"
    description: "Detailed Markdown report outlining detected deprecations, applied migrations, backup paths, and health status."
safety:
  human_in_the_loop: false
  sandboxed_execution: true
tools:
  - "file_read_tool"
  - "file_write_tool"
  - "file_edit_tool"
  - "grep_tool"
verification_steps:
  - step_id: "deprecation_fingerprint_scanned"
    description: "Scan target files against deprecation pattern catalog (e.g. legacy snake_case env vars, bare tools, missing contract steps)"
    validation_method: "Audit diagnostic output for coverage across all scanned YAML frontmatter blocks"
    is_required: true
  - step_id: "preflight_backup_created"
    description: "Ensure atomic backup files (.bak) are created before mutating any source file"
    validation_method: "Verify file existence of original snapshots prior to write operations"
    is_required: true
  - step_id: "in_place_fix_validated"
    description: "Verify mutated files parse successfully as valid YAML and comply with current schema"
    validation_method: "Re-parse updated frontmatter using standard YAML parser without syntax errors"
    is_required: true
  - step_id: "doctor_health_check_passed"
    description: "Confirm all deprecation warnings are cleared post-fix"
    validation_method: "Assert zero remaining deprecation diagnostics in post-migration audit pass"
    is_required: true
---

# Deprecated Plugin Syntax Migration & Doctor Auto-Fix Protocol

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


The `plugin-syntax-migrator` skill automates the modernization, schema normalization, and non-destructive upgrading of legacy plugin manifests and `SKILL.md` frontmatters.

## The Zero-Downtime Migration Philosophy

Platform frameworks evolve rapidly. Breaking changes in tool declarations, permission schemas, or environment mappings must never leave users with broken agents.
This skill adheres to three core tenets:
1. **Never Break Without Backup**: Every in-place mutation creates a timestamped `.bak` replica.
2. **Deterministic Transpilation**: Transformations strictly follow approved syntax mapping tables.
3. **Atomic Verification**: Changes are re-scanned immediately; if a syntax error is introduced, the file rolls back automatically.

---

## 4-Phase Migration & Auto-Fix SOP

```
Target Skills / Plugins Directory
  │
  ▼
[Phase 1: Deprecation Fingerprint Scanning] ── AST & Regex scan against legacy rule catalog
  │
  ▼
[Phase 2: Diff Matrix & Risk Assessment] ── Synthesize Before vs After preview & risk tiers
  │
  ▼
[Phase 3: Atomic In-Place Patching & Backup] ── Write .bak snapshot and apply normalized YAML
  │
  ▼
[Phase 4: Post-Fix Validation & Doctor Check] ── Re-parse schema, confirm zero warnings, emit report
```

### Phase 1: Deprecation Fingerprint Scanning

1. **Target Discovery**:
   - Locate all `SKILL.md`, `plugin.json`, and `manifest.yaml` files within the target directory.
2. **Rule Matrix Matching**:
   Inspect YAML frontmatter against the SSOT deprecation catalog:
   - `primary_env` ➔ Normalize to `primaryEnv` (preserving alias compatibility where needed).
   - `oauth-issuer` ➔ Normalize to `oauth_issuer` with `required_oauth_issuers` array syntax.
   - Bare tool names (`bash`, `file_read`) ➔ Upgrade to standard canonical names (`bash_code_execute_tool`, `file_read_tool`).
   - Missing `contract` block ➔ Generate standardized 4-phase contract scaffold.
   - Legacy `allowed-tools` string ➔ Convert to standard list sequence or space-delimited canonical form.

### Phase 2: Diff Matrix & Risk Assessment

Before applying disk changes, generate a structured migration plan:
- **Non-Breaking Upgrades**: Renaming fields, formatting lists, adding missing standard tags.
- **Structural Upgrades**: Splitting merged fields, generating verification steps.
- Present a concise diff table:
  ```markdown
  | File | Deprecated Pattern | Target Standard | Risk Tier |
  |---|---|---|---|
  | `skills/foo/SKILL.md` | `primary_env: KEY` | `primaryEnv: KEY` | Safe |
  | `skills/bar/SKILL.md` | `allowed-tools: bash` | `tools: [bash_code_execute_tool]` | Safe |
  ```

### Phase 3: Atomic In-Place Patching & Backup

1. **Create Snapshot Backup**:
   - Copy `{filename}` to `{filename}.bak`.
2. **Execute In-Place Mutation**:
   - Use `file_edit_tool` or `file_write_tool` to apply normalized syntax while preserving Markdown formatting and comments.
   - Keep character encoding UTF-8 with standard `\n` line endings.

### Phase 4: Post-Fix Validation & Doctor Check

1. **Schema Re-parse**:
   - Parse mutated files to guarantee YAML syntactical validity.
2. **Doctor Health Verification**:
   - Verify that all deprecation flags for the target files evaluate to green (`PASS`).
3. **Emit `migration_report.md`**:
   - Document total files scanned, files updated, backups retained, and zero-defect confirmation.
