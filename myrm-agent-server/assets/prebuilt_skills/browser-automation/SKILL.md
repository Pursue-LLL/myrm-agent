---
name: browser-automation
description: >-
  General browser automation operating loop for GUI web tasks — navigation, forms,
  SSO login, 2FA handoff, tabs, and downloads. Distinct from data-scraping pipelines.
version: 1.0.0
category: automation
tags:
  - browser
  - automation
  - forms
  - sso
  - gui
allowed-tools: browser_navigate_tool browser_inspect_tool browser_snapshot_tool browser_interact_tool browser_extract_tool browser_manage_tool browser_execute_script_tool browser_ask_human_tool
contract:
  steps:
    - "Orient — check tabs/status; navigate to target URL"
    - "Perceive — inspect or snapshot; capture element refs"
    - "Act — interact using refs from the latest snapshot"
    - "Verify — resnapshot after major UI changes; recover stale refs once"
    - "Handoff — use browser_ask_human for 2FA, CAPTCHA, or payment gates"
  potential_traps:
    - description: "Acting on stale element refs after DOM changes"
      mitigation: "Resnapshot after navigation or major UI updates; retry interact once, then resnapshot"
      severity: high
    - description: "Guessing through login or payment screens"
      mitigation: "Call browser_ask_human_tool and wait for user takeover"
      severity: high
  verification_steps:
    - step_id: page_ready
      description: "Target page or form is visible"
      validation_method: "Snapshot shows expected controls or post-action extract confirms content"
      is_required: true
  success_criteria: "Task completed on the correct page with verified outcome or explicit user handoff"
  estimated_duration_seconds: 600
---

# Browser Automation

## Overview

Use this skill for interactive web work: logging into sites, filling forms, exporting reports, managing tabs, and handling blockers. For structured data extraction pipelines, prefer the **web-scraping** skill instead.

## Operating Loop

1. **Navigate** — `browser_navigate_tool` to open the target URL.
2. **Perceive** — `browser_inspect_tool` for a quick read, or `browser_snapshot_tool` before any interaction.
3. **Act** — `browser_interact_tool` using refs from the **latest** snapshot (click, fill, scroll, upload).
4. **Extract** — `browser_extract_tool` when you need text, screenshots, or media URLs.
5. **Manage** — `browser_manage_tool` for tabs, downloads, dialogs, session vault, or PDF.
6. **Batch** — `browser_execute_script_tool` only when a short script is faster than many single actions.
7. **Handoff** — `browser_ask_human_tool` for 2FA, CAPTCHA, payment, or camera/mic prompts.

## Rules

- Snapshot before interact; resnapshot after navigation or layout changes.
- If a ref is stale, recover once, then resnapshot — do not loop blindly.
- Prefer `web_fetch_tool` or `web_search_tool` when static fetch is enough (faster, cheaper).
- Report blockers clearly instead of guessing credentials or payment steps.

## Parallel Work

When the main task also needs research or analysis, delegate those parts to specialized sub-agents while you handle browser steps directly or via the **browser** sub-agent preset.
