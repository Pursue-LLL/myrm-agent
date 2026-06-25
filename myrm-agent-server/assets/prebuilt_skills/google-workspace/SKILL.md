---
name: google-workspace
description: >-
  Google Workspace integration for Calendar, Gmail, and Drive via OAuth-connected
  user credentials. Uses Google REST APIs through bash_code_execute_tool with
  auto-injected tokens (never expose secrets to chat).
version: 1.0.0
category: productivity
tags:
  - google
  - calendar
  - gmail
  - drive
  - workspace
  - productivity
allowed-tools: bash_code_execute_tool web_fetch_tool file_write_tool
contract:
  steps:
    - "Phase 1: Verify — confirm Google Workspace OAuth is connected in Settings"
    - "Phase 2: Discover — identify target API (Calendar / Gmail / Drive) and scope"
    - "Phase 3: Execute — call Google REST API with injected bearer token"
    - "Phase 4: Confirm — summarize results; confirm destructive actions with user"
  potential_traps:
    - description: "OAuth not connected or token expired without refresh"
      mitigation: "Ask user to connect Google Workspace in Settings → Integrations → Credentials before proceeding"
      severity: high
    - description: "Exposing OAuth tokens in LLM context or logs"
      mitigation: "Never print $GOOGLE_WORKSPACE_TOKEN. Use bash with allowed_issuers google_workspace only."
      severity: critical
    - description: "Destructive Gmail/Drive/Calendar mutations without confirmation"
      mitigation: "Default to read-only endpoints; confirm before create/update/delete"
      severity: high
  verification_steps:
    - step_id: oauth_connected
      description: "Google Workspace OAuth credential is available for this session"
      validation_method: "bash test -n \"$GOOGLE_WORKSPACE_TOKEN\" succeeds with allowed_issuers google_workspace"
      is_required: true
  success_criteria: "Requested Google Workspace operation completed with user-visible summary"
  estimated_duration_seconds: 180
---

# Google Workspace

## Overview

Access the user's Google Calendar, Gmail, and Drive through official Google REST APIs. Tokens are injected at runtime from the user's OAuth connection — **never** ask the user to paste tokens into chat.

## Prerequisites

1. User connects **Google Workspace** in **Settings → Integrations → Credentials** (OAuth flow auto-enables this skill unless previously disabled).
2. Server must have `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` configured.

If OAuth is missing, stop and instruct the user to connect first.

## Helper Script

Bundled readonly CLI (stdlib Python). Run from the staged skill path in the sandbox:

```bash
python3 .claude/skills/google-workspace/scripts/google_api.py calendar-today
python3 .claude/skills/google-workspace/scripts/google_api.py gmail-inbox
python3 .claude/skills/google-workspace/scripts/google_api.py drive-recent
```

The bash executor stages the skill into the workspace and rewrites these to relative `scripts/` paths automatically.

Always run via `bash_code_execute_tool` with `allowed_issuers: ["google_workspace"]`.

## Secret Safety (MANDATORY)

- **Never** print, log, or echo `$GOOGLE_WORKSPACE_TOKEN`
- **Never** read credential files from disk
- Use `bash_code_execute_tool` with `allowed_issuers: ["google_workspace"]` so the token is injected securely
- Prefer read-only API calls unless the user explicitly requests a write action

- Prefer the helper script over hand-written curl

## Calendar

```bash
python3 .claude/skills/google-workspace/scripts/google_api.py calendar-today
```

## Gmail

Returns recent INBOX messages with `subject`, `from`, `snippet`, and `internalDate` (one Gmail API call per message for metadata).

```bash
python3 .claude/skills/google-workspace/scripts/google_api.py gmail-inbox
```

## Drive

```bash
python3 .claude/skills/google-workspace/scripts/google_api.py drive-recent
```

## Error Handling

| HTTP | Meaning | Action |
|------|---------|--------|
| 401 | Token invalid/expired | Ask user to reconnect Google Workspace in Settings |
| 403 | Insufficient scope | Reconnect OAuth to grant Calendar/Gmail/Drive scopes |
| 429 | Rate limited | Back off and retry once |

## Write Operations

Only perform create/update/delete when the user explicitly requests it. Show a draft summary and get confirmation before mutating data.
