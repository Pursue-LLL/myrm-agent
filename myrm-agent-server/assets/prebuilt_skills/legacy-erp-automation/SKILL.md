---
name: legacy-erp-automation
description: >-
  Automate legacy Windows business systems without APIs (SAP GUI, custom ERP,
  FoxPro-era apps): snapshot-first desktop control, vault-backed login,
  vision fallback, and delivery verification. Designed for unattended Cron
  runs (invoice download, report export, form entry).
version: 1.0.0
category: office
tags:
  - erp
  - sap
  - legacy-windows
  - desktop-automation
  - cron
  - unattended
  - invoice
  - report
allowed-tools: desktop_snapshot_tool desktop_interact_tool desktop_vision_tool file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Snapshot First — call desktop_snapshot_tool before every action batch; drive by element references, never by memorized coordinates"
    - "Phase 2: Empty-Tree Fallback — when the snapshot carries no usable tree (FoxPro or owner-drawn UI), switch to desktop_vision_tool screenshot guidance and re-anchor after every screen change"
    - "Phase 3: Vault-Only Login — sign in exclusively via the fill_credential vault action; never type, paste, or read back secrets"
    - "Phase 4: Act Serially — one mutating desktop action at a time; wait for the window to settle before the next snapshot"
    - "Phase 5: Delivery Verification — confirm the expected file, export, or submitted form exists before reporting success"
    - "Phase 6: Unattended Discipline — for Cron runs, require pre-trusted app identity; on any unexpected dialog, stop and file for human review instead of guessing"
  potential_traps:
    - description: "Acting on stale element references after the window redraws"
      mitigation: "Re-snapshot after every navigation, popup, or loading spinner; treat references as single-use."
      severity: high
    - description: "Secrets typed or echoed into visible fields and logs"
      mitigation: "fill_credential only; never use type actions for passwords, and never repeat credential values in replies."
      severity: high
    - description: "Double-submitting forms on retry (duplicate invoices or postings)"
      mitigation: "Check for the success state first; retries must be idempotent — verify before re-clicking submit."
      severity: medium
    - description: "Silent no-op when the target app is not yet fully loaded"
      mitigation: "Wait for the main window marker element before the first action; fail loud with the observed screen state."
      severity: medium
  verification_steps:
    - step_id: snapshot_before_act
      description: "Every action batch is preceded by a fresh snapshot or a vision re-anchor"
      validation_method: "Trace shows snapshot/vision call immediately before each interact call"
      is_required: true
    - step_id: vault_login_only
      description: "No secret appears as typed text in the trace"
      validation_method: "Login steps use fill_credential; no password literals in actions or replies"
      is_required: true
    - step_id: delivery_confirmed
      description: "The invoice file, report export, or submitted form is confirmed present"
      validation_method: "Output names the delivered artifact and where to find it"
      is_required: true
    - step_id: unattended_stop_rule
      description: "Unexpected dialogs stop the run for human review instead of guessing"
      validation_method: "Trace ends with a review request, not repeated blind clicks"
      is_required: false
  success_criteria: "The requested legacy-system task completes with a verified deliverable, no secret exposure, and no duplicate submissions"
  estimated_duration_seconds: 300
---

# Legacy ERP Automation

Operate Windows business software that offers no API, the way a careful
operator would — look first, sign in safely, act once, verify the delivery.

## Operating rules

1. **Snapshot before every batch.** Call `desktop_snapshot_tool` first and
   drive by its element references. Coordinates from memory are forbidden.
2. **Empty tree means vision mode.** Legacy toolkits (FoxPro, owner-drawn
   controls) expose no accessibility tree — switch to `desktop_vision_tool`,
   act, then re-anchor. Never assume the screen stayed still.
3. **Credentials live in the vault.** Log in only through the
   `fill_credential` action. Passwords must never be typed, pasted, quoted
   back, or written to files.
4. **One mutation at a time.** Desktop actions serialize; wait for redraws
   between steps. If a dialog you did not expect appears, stop the run and
   ask for human review — unattended runs must never guess through popups.
5. **Prove delivery.** Downloads, exports, and form submissions count only
   when the file or confirmation is observed. Say where the artifact is.

## Unattended (Cron) notes

- The target application must be pre-trusted before scheduling; an untrusted
  app blocks the run instead of prompting at 3 AM.
- Prefer idempotent checks ("already downloaded?") over blind re-runs so a retry never posts the same invoice twice.

## Handoff checklist for the requester

- Which application and window title to open.
- What "done" looks like (file name, report tab, confirmation number).
- Login is handled by the vault — do not send passwords in chat.
