---
name: imap-smtp-email
description: >-
  Manage personal email accounts via IMAP/SMTP: check inbox, search messages,
  read full content, download attachments, send and reply. Works with any
  provider (163, QQ Mail, Outlook, Yahoo, corporate Exchange, etc.).
version: 1.0.0
category: productivity
tags:
  - email
  - imap
  - smtp
  - inbox
  - productivity
allowed-tools: bash_code_execute_tool file_write_tool
requires:
  env: [EMAIL_IMAP_HOST, EMAIL_IMAP_USER, EMAIL_IMAP_PASSWORD]
contract:
  steps:
    - "Phase 1: Verify — confirm email credentials are configured"
    - "Phase 2: Connect — establish IMAP connection and validate access"
    - "Phase 3: Execute — perform the requested email operation"
    - "Phase 4: Report — summarize results clearly to the user"
  potential_traps:
    - description: "Credentials not configured or authorization code expired"
      mitigation: "Check env vars first; instruct user to configure in Settings → Skills → Environment"
      severity: high
    - description: "Exposing email credentials in LLM context"
      mitigation: "Never print or echo credential env vars. Runtime injects them into bash process automatically."
      severity: critical
    - description: "Sending emails without user confirmation"
      mitigation: "Always confirm recipient, subject, and body with user before executing send/reply"
      severity: high
    - description: "163/NetEase requires IMAP ID command after login"
      mitigation: "The script handles RFC 2971 ID automatically for all connections"
      severity: medium
  verification_steps:
    - step_id: credentials_available
      description: "IMAP host, user, and password environment variables are set"
      validation_method: "bash test -n \"$EMAIL_IMAP_HOST\" && test -n \"$EMAIL_IMAP_USER\" && test -n \"$EMAIL_IMAP_PASSWORD\""
      is_required: true
  success_criteria: "Requested email operation completed with user-visible summary"
  estimated_duration_seconds: 120
---

# IMAP/SMTP Email

## Overview

Manage personal email via standard IMAP/SMTP protocols. Supports any email provider that offers IMAP access (163, QQ Mail, Outlook, Yahoo, corporate Exchange, Fastmail, ProtonMail Bridge, etc.).

## Prerequisites

Configure email credentials in **Settings → Skills → Environment Variables** for this skill:

| Variable | Description | Example |
|----------|-------------|---------|
| `EMAIL_IMAP_HOST` | IMAP server hostname | `imap.163.com` |
| `EMAIL_IMAP_USER` | Login username (usually email address) | `user@163.com` |
| `EMAIL_IMAP_PASSWORD` | Password or app-specific authorization code | `ABCDEFGHIJKLMNOP` |
| `EMAIL_SMTP_HOST` | SMTP server hostname (optional, for sending) | `smtp.163.com` |
| `EMAIL_SMTP_USER` | SMTP login (defaults to IMAP user) | `user@163.com` |
| `EMAIL_SMTP_PASSWORD` | SMTP password (defaults to IMAP password) | `ABCDEFGHIJKLMNOP` |
| `EMAIL_IMAP_PORT` | IMAP port (default: 993) | `993` |
| `EMAIL_SMTP_PORT` | SMTP port (default: 587) | `587` |

Most providers use the same credentials for IMAP and SMTP. Only set SMTP variables if they differ.

## Helper Script

```bash
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py check
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py check --unread-only --limit 10
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py search --from boss@company.com --since 7d
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py search --subject "contract" --since 30d
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py read MESSAGE_UID
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py download MESSAGE_UID
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py download MESSAGE_UID --filename "contract.pdf"
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py mark-read 123,456,789
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py mark-unread 123
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py send --to recipient@example.com --subject "Subject" --body "Content"
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py reply --uid MESSAGE_UID --body "Reply content"
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py folders
```

Run via `bash_code_execute_tool`. Credentials are injected as environment variables at runtime — **never** ask the user to paste credentials into chat.

## Secret Safety (MANDATORY)

- **Never** print, log, or echo `$EMAIL_IMAP_PASSWORD` or `$EMAIL_SMTP_PASSWORD`
- **Never** include credentials in code blocks shown to the user
- Credentials are runtime-injected — do not ask for manual input
- Prefer read-only operations unless user explicitly requests send/reply

## Common Workflows

### Check Inbox
```bash
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py check --unread-only --limit 20
```

### Search by Sender
```bash
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py search --from sender@example.com --since 7d
```

### Read and Summarize
```bash
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py read 12345
```

### Download Attachment
```bash
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py download 12345
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py download 12345 --filename "report.pdf"
```

### Mark as Read (useful after cron processing)
```bash
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py mark-read 12345,12346,12347
```

### Send Email (confirm with user first!)
```bash
python3 .claude/skills/imap-smtp-email/scripts/email_manager.py send --to user@example.com --subject "Meeting Notes" --body "Here are the notes..."
```

## Error Handling

| Error | Cause | Action |
|-------|-------|--------|
| Authentication failed | Wrong password or expired auth code | Ask user to update credentials in Settings |
| Connection refused | Wrong host/port or network issue | Verify host and port settings |
| IMAP ID required | 163/NetEase needs ID command | Handled automatically by script |
| Mailbox not found | Invalid folder name | Use `folders` command to list available folders |

## Provider Quick Reference

| Provider | IMAP Host | SMTP Host | Notes |
|----------|-----------|-----------|-------|
| 163 | imap.163.com | smtp.163.com | Enable IMAP in settings, use authorization code |
| QQ Mail | imap.qq.com | smtp.qq.com | Enable IMAP in settings, use authorization code |
| Outlook | outlook.office365.com | smtp.office365.com | Use app password if 2FA enabled |
| Yahoo | imap.mail.yahoo.com | smtp.mail.yahoo.com | Generate app password |
| Gmail | imap.gmail.com | smtp.gmail.com | Use app password (prefer google-workspace skill) |
| Fastmail | imap.fastmail.com | smtp.fastmail.com | Use app password |
| Corporate | Check IT docs | Check IT docs | Often requires VPN or specific ports |
