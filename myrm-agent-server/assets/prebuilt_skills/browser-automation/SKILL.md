---
name: browser-automation
description: >-
  Enterprise-grade browser automation operating loop for GUI web tasks — standard navigation,
  multi-field forms, complex rich-editor/canvas apps (Docs, Sheets, Feishu, Notion, Figma),
  SSO/MFA handoffs, and visual verification.
version: 1.1.0
category: automation
tags:
  - browser
  - automation
  - forms
  - sso
  - gui
  - visual-workflow
allowed-tools: browser_navigate_tool browser_inspect_tool browser_snapshot_tool browser_interact_tool browser_extract_tool browser_manage_tool browser_execute_script_tool browser_ask_human_tool
contract:
  steps:
    - "Orient & Assess — inspect tabs and layout; detect canvas or rich-editor indicators"
    - "Route Track — select Standard DOM, Visual Coordinate, or Script-First Batching"
    - "Act & Probe — perform ref actions, coordinate clicks with Write Probe, or batched steps"
    - "Verify — execute visual goal verification or resnapshot after DOM transformations"
    - "Handoff — immediately delegate 2FA, SMS code, CAPTCHA, or payment walls to human"
  potential_traps:
    - description: "Blindly typing into complex rich editors (Feishu, Google Docs, Notion) without activation"
      mitigation: "Switch to Visual Coordinate mode; run Write Probe with physical keydown press before bulk input"
      severity: high
    - description: "Over-scripting simple sequential interactions into blackbox scripts"
      mitigation: "Strictly gate Script mode to >=3 deterministic same-page form fields; enforce max 8 steps per script"
      severity: medium
    - description: "Guessing passwords or attempting to automate through 2FA/SMS/MFA challenges"
      mitigation: "Immediately call browser_ask_human_tool and wait for user takeover via BrowserLiveView"
      severity: critical
    - description: "Acting on stale element refs after layout re-render or dynamic pagination"
      mitigation: "Resnapshot after navigation or major UI updates; recover stale refs once, then refresh"
      severity: high
    - description: "Using main viewport coordinates for deep cross-origin iframe canvas apps"
      mitigation: "If target canvas is hosted inside an iframe (e.g. f1_e2), ensure viewport coordinates account for iframe offset"
      severity: medium
  verification_steps:
    - step_id: interaction_verified
      description: "Action outcome is confirmed through visual verifier or snapshot comparison"
      validation_method: "Pass verify_goal to interact/execute_script or compare snapshot elements"
      is_required: true
    - step_id: security_gated
      description: "No sensitive credentials or payment screens are blindly submitted"
      validation_method: "Verified that browser_ask_human_tool is invoked upon any 2FA or CAPTCHA prompt"
      is_required: true
  success_criteria: "Target workflow completed with verified visual outcome, zero credential guessing, and clean session state"
  estimated_duration_seconds: 600
---

# Browser Automation

## Overview

Use this skill for interactive web work: logging into sites, filling complex forms, navigating enterprise systems, manipulating online collaborative documents, and handling interactive blockers. For bulk unstructured web scraping pipelines, prefer the **web-scraping** skill instead.

---

## Three-Track Decision Tree

Before interacting, examine the page snapshot structure to select the optimal track:

```
                  ┌───────────────────────────────┐
                  │    Evaluate Page Snapshot     │
                  └──────────────┬────────────────┘
                                 │
         ┌───────────────────────┼────────────────────────┐
         ▼                       ▼                        ▼
 [Standard HTML DOM]   [[VISUAL_CONTENT_DETECTED]]   [Deterministic Multi-Field Form]
  Links, Buttons,       Canvas, Figma, Feishu,        >=3 fields on the same page
  Native Inputs         Google Docs / Sheets          (e.g., invoice/reimbursement)
         │                       │                        │
         ▼                       ▼                        ▼
   【TRACK 1】             【TRACK 2】              【TRACK 3】
 Standard DOM Track      Visual Coordinate Track   Script-First Batch Track
 `browser_interact`     `interact_at` / `x, y`    `steps[]` or `execute_script`
  via element refs      + Write Probe Protocol    + `verify_goal` validation
```

---

## Track 1: Standard DOM Semantic Track

Use for standard web pages where inputs and clickable controls are native HTML elements with clear ARIA refs.

1. **Snapshot**: Call `browser_snapshot_tool` to obtain element refs (`e0`, `e1`, `f1_e2`).
2. **Interact**: Call `browser_interact_tool` with the targeted `ref` and `action` (`click`, `fill`, `select`, `check`).
3. **Verify**: Provide `verify_goal` (e.g. `'Search results dropdown visible'`) to automatically verify the action visually, or take a fresh snapshot if the layout shifts.

*Rule*: If an element ref reports stale, recover once with a fresh snapshot. Never loop blindly on failed refs.

---

## Track 2: Visual Coordinate Track (Canvas & Rich Editors)

Use when manipulating canvas-rendered tools or modern rich-text editors (e.g., **Google Docs, Google Sheets, Feishu/Lark Docs, Notion, Figma, Miro, Canva**) where standard DOM inputs are absent or snapshot outputs `[VISUAL_CONTENT_DETECTED]`.

### 1. Viewport Coordinate Interaction
Bypass DOM ref resolution by supplying CSS viewport coordinates directly to `browser_interact_tool`:
- Provide `x` and `y` (CSS viewport pixels).
- Do **NOT** provide `ref` when using coordinate mode.
- Use `action: "click"` to focus, `action: "dblclick"` to select words, or `action: "drag"` with `target_x, target_y` for canvas items.

### 2. Write Probe Protocol (Mandatory for Rich Editors)
Modern rich editors rely on internal state machines that listen to physical keyboard events rather than simple DOM value updates. **Never blind-type full paragraphs into rich editors without probing.**
1. **Focus Click**: Click the target editor coordinate `(x, y)`.
2. **Probe Keystroke**: Send a physical key combo using `action: "press", text: "Enter"` or a probe keystroke `action: "type", text: " "` to verify cursor activation.
3. **Clear & Replace (If Existing Content/Placeholder)**: When clearing default placeholders or previous text, explicitly issue `action: "press", text: "Control+a"` (or `"Meta+a"` on macOS) followed by `action: "press", text: "Backspace"` to guarantee clean text entry.
4. **Verification**: Check that the cursor is active or content area is empty/ready.
5. **Input Content**: Type text using `action: "type"` with real keystroke simulation, accompanied by `verify_goal` (e.g. `'Document shows newly inserted meeting summary'`).

---

## Track 3: Script-First Batch Processing Track

Use for high-density, multi-field workflows on the same page (e.g., entering 5+ fields in an ERP, reimbursement form, or CRM).

### 1. Eligibility Guard & Priority Hierarchy (Strictly Enforced)
- **Eligibility Threshold**: Only enter Track 3 if there are **>=3 deterministic actions** on the **same page** (e.g., fill input A, fill input B, select dropdown C).
- **Priority Hierarchy**: **Always 100% prioritize Declarative Batching (`steps[]`) over programmatic script execution.** `steps[]` is strictly validated by Pydantic models with bounded per-step timeout and credential masking.
- **Prohibition**: Do **NOT** write arbitrary long scripts for simple 1-2 step navigations, and never use `execute_script` where `steps[]` can accomplish the task.

### 2. Declarative Batching (`steps[]` - Preferred Standard)
Prefer declarative batching in `browser_interact_tool` using the `steps` parameter:
```json
{
  "steps": [
    {"action": "fill", "ref": "e3", "text": "INV-2026-0901"},
    {"action": "fill", "ref": "e5", "text": "8500.00"},
    {"action": "select", "ref": "e7", "text": "Software License"},
    {"action": "click", "ref": "e9", "verify_goal": "Form validation passed and submit enabled"}
  ]
}
```

### 3. Programmatic Script Execution (`browser_execute_script_tool` - Dynamic Fallback Only)
Reserved exclusively when complex DOM arithmetic, dynamic loop evaluations, or deeply nested iframe traversal are strictly unavoidable:
- Keep scripts concise, idempotent, and bounded (**max 8 interaction steps** per script call).
- Always include `verify_goal` parameter to trigger automatic baseline screenshot comparison by `_vision_verifier`.
- **Fail-Fast**: If the script encounters an error or verification fails, abort batching immediately and downgrade to Track 1 single-step interaction.

---

## Sensitive Gate & Human Handoff (HITL)

When interacting with authenticated web systems, you may encounter security gates that AI must never guess or bypass autonomously.

### 1. Mandatory Handoff Triggers
Immediately stop automated actions and call `browser_ask_human_tool` upon encountering:
- **Two-Factor Authentication (2FA / MFA)** prompts (SMS verification code, Authenticator TOTP push, security keys);
- **CAPTCHA / Cloudflare Turnstile / Geetest** slider challenges;
- **Financial Payment Confirmations** (bank transfer, credit card CVV, payment QR codes);
- **Enterprise SSO Consent** requiring biometric or external hardware key confirmation.

### 2. Handoff Protocol
1. Call `browser_ask_human_tool` with a clear explanation of what the user needs to do in the WebUI `BrowserLiveView` (e.g., *"Please complete the SMS verification code on the screen and click Continue"*).
2. The user will interact with the browser directly through the LiveView or Extension interface.
3. Once the user signals completion, take a fresh snapshot to verify that the authentication wall is cleared before resuming automation.
4. **Zero Guessing Rule**: Never attempt to guess one-time passwords, answers to security questions, or financial credentials.

---

## Diagnostics & Health Escalation

If browser tools repeatedly report connection errors, timeouts, or sandbox disconnections across consecutive turns:
1. Do not loop blindly on repeated navigation or interaction calls.
2. Report the anomaly to the user and suggest running the browser diagnostic tool or visiting the system settings (`/api/v1/health/browser/doctor`) to verify sandbox health.

