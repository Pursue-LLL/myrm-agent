---
name: workspace-auto-organizer
description: >-
  Scan a workspace folder, classify files by topic/date/type, and write an
  organize-plan.json for human review before batch move (never mv directly).
version: 1.0.0
category: productivity
tags:
  - workspace
  - organize
  - files
  - vault
allowed-tools: glob_tool file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: glob scan the user-specified scope folder (max 500 files)"
    - "Phase 2: Sample-read representative files to infer categories"
    - "Phase 3: Write {scope}.organize-plan.json with src, dst, reason per item"
    - "Phase 4: Tell user to open the plan artifact and click Apply in WebUI"
  success_criteria: "Valid organize-plan.json with every item inside scope and depth <= 3"
  estimated_duration_seconds: 600
---

# Workspace Auto-Organizer

Produce a **reviewable organize plan** for a workspace folder. **Do not** run `mv`, `cp`, or `bash_code_execute_tool` to move files — the user applies moves via WebUI after editing the plan.

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters) and **`command`**. Put `reason` first.

## Workflow

1. Confirm the **scope folder** (workspace-relative), e.g. `chat_abc/` or vault inbox `.`
2. **Scan** with `glob_tool` ( cap at 500 files ).
3. **Sample-read** ambiguous files with `file_read_tool` (do not read huge binaries).
4. Build destinations with **max depth 3** from scope, e.g. `2026/reports/`, `images/screenshots/`.
5. Every item needs a **reason** (one short sentence, user-facing language).
6. Write JSON plan:

```json
{
  "version": 1,
  "scope_root": "chat_abc",
  "preset": "project",
  "items": [
    {
      "src": "chat_abc/report.md",
      "dst": "chat_abc/research/report.md",
      "reason": "Research markdown grouped under research/",
      "src_mtime_ns": 1710000000000000000
    }
  ]
}
```

Use `stat` via a one-line python snippet in bash **only** to fill `src_mtime_ns` if needed, or omit the field.

7. Save as `{scope}.organize-plan.json` beside the scope folder using `file_write_tool`.
8. Tell the user to open the plan artifact in chat → review the table → **Apply** or **Rollback** if needed.

## Presets

| preset | Use when |
|--------|----------|
| `date` | Group by year/month |
| `ext` | Group by file type |
| `project` | Group by topic/project name |
| `custom` | Mixed rules — explain in reasons |

## Rules

- Never move `.git`, `.env*`, or `*.organize-plan.json`.
- Never propose destinations outside `scope_root`.
- Prefer merging singletons — avoid one-file folders when possible.
- If scope has ≤5 files, suggest manual move in File Browser instead of a plan.
