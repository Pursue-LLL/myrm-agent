---
name: relationship-signal-promoter
description: >-
  Identify interpersonal relationship, networking, and social intention signals
  (casual follow-ups, coffee chats, favors, mutual introductions) from conversations.
  Protects work boards against non-work task pollution with a strict Manual Promotion Gate,
  surfacing structured Signal Cards that require explicit human approval before being added to Kanban.
version: 1.0.0
category: productivity
tags:
  - relationship
  - networking
  - task-management
  - kanban
  - hitl
  - social-signals
  - 人际交往
  - 待办门禁
  - 关系沉淀
allowed-tools: kanban_add_task kanban_list_tasks file_write_tool file_read_tool memory_save_tool
contract:
  steps:
    - "Phase 1: Signal Sensing & Triage — Distinguish formal work deliverables from casual social invitations and vague intentions"
    - "Phase 2: Signal Card Construction — Extract persona, intention, context, and suggested window into a lightweight digest"
    - "Phase 3: Manual Promotion Gate — Strictly hold all signals in review mode awaiting explicit user command to promote"
    - "Phase 4: Standardized Kanban Dispatch — On confirmed promotion, dispatch to Kanban with [RELATIONSHIP] prefix and metadata"
  potential_traps:
    - description: "Polluting work kanban boards with casual social chatter or vague promises"
      mitigation: "Strict manual promote gate: NEVER autonomously call kanban_add_task for social/casual signals without explicit user consent"
      severity: high
    - description: "Overly rigid deadlines for casual social engagements causing notification fatigue"
      mitigation: "Default to flexible timeframes (e.g. 'Within 2 weeks', 'Next month') rather than hard calendar deadlines"
      severity: medium
    - description: "Loss of social context during task promotion"
      mitigation: "Preserve original conversation snippet, interlocutor identity, and initial promise context in task description"
      severity: low
  verification_steps:
    - step_id: zero_auto_kanban_pollution
      description: "Verify no kanban tasks are created for informal social signals without explicit user approval"
      validation_method: "Inspect agent instructions for manual gate enforcement"
      is_required: true
    - step_id: signal_card_schema_conformance
      description: "Extracted signals include Contact, Commitment, Context, and Suggested Follow-up Window"
      validation_method: "Check structured signal card schema in response"
      is_required: true
  success_criteria: "Informal promises and networking signals are cleanly cataloged without cluttering active work streams, awaiting human promote decisions."
  estimated_duration_seconds: 120
---

# Relationship Signal Manual Promote To Work Gate

## Overview

In daily communications, voice recordings, and messaging streams, users frequently exchange informal promises and networking intentions:
- *"Let's grab lunch sometime next week to chat about partnerships."*
- *"Remind me to share that deck when I get back to the office."*
- *"We should introduce Alex to our mutual friend in design."*

If an AI aggressively turns every casual remark into a formal Kanban work task, the user's primary work board quickly becomes cluttered with low-urgency, ambiguous social obligations, leading to alert fatigue and anxiety in non-work settings.

This skill enforces a **Manual Promotion Gate**: it acts as an intelligent, quiet listener that extracts interpersonal commitment signals, formats them into a clean **Relationship Signal Card**, and **holds them in check** until the user explicitly commands: *"Add this to my Kanban"* or *"Promote to work task"*.

---

## 1. Operating Protocol

### Phase 1: Signal Sensing & Triage

When reviewing transcripts, messages, or meeting notes, categorize action items into two distinct streams:

| Stream | Criteria | Autonomous Handling |
| --- | --- | --- |
| **Formal Work Task** | Tangible deliverables, clear work context, explicit sprint/project ownership, deadlines | Follow standard `task-planning` or `voice-memo-synthesizer` SOP |
| **Relationship Signal** | Social meetups, coffee chats, casual favors, exploratory intros, vague follow-ups | **HALT at Gate** — Produce Signal Card; DO NOT call `kanban_add_task` |

### Phase 2: Signal Card Construction

Package detected interpersonal commitments into a standardized Markdown summary:

```markdown
### 🤝 人际沟通意向信号 (Relationship Signals)

| 意向对象 | 约定/跟进事项 | 原始语境与承诺 | 建议跟进窗口 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| **张总 (Acme Corp)** | 约线下咖啡交流 | *"下周二后有空约个咖啡聊聊出海规划"* | 下周 (7-14天内) | 待确认 (未入看板) |
| **王敏 (产品线)** | 发送竞品调研脱敏摘要 | *"回头把那个工具链对比表转我一份"* | 本周内 (3-5天内) | 待确认 (未入看板) |

> 💡 **提示**：以上为人际协作与社交意向信号，尚未写入正式工作看板。如需追踪，可直接回复：
> - `全部转入看板` 或 `将张总转为待办`
```

### Phase 3: Manual Promotion Gate (Strict HITL)

- **NEVER** call `kanban_add_task` autonomously during Phase 1 or Phase 2.
- The gate remains closed until the user provides clear affirmation:
  - *"把张总那个加进待办"*
  - *"确认转入看板"*
  - *"Promote signal 1 to work"*

### Phase 4: Standardized Kanban Dispatch

Upon receiving user confirmation, execute `kanban_add_task` with the following conventions:

1. **Title Prefix**: Always prepend `[人际跟进]` or `[Relationship]` to maintain visual separation from engineering/business tasks.
   - Example: `[人际跟进] 约张总线下咖啡 (出海规划交流)`
2. **Task Metadata**:
   - `priority`: Default to `low` or `medium` (never `urgent` unless explicitly instructed).
   - `labels`: `["relationship", "networking"]`.
   - `description`: Include the contact name, original conversation excerpt, and expected conversation goal.
3. **Idempotency**: Use deterministic key format: `f"rel:{contact_slug}:{date_slug}"` to prevent accidental duplicates.

---

## 2. Anti-Patterns & Traps

1. **Zero Unconfirmed Kanban Writing**:
   - Calling `kanban_add_task` on a vague "let's hang out" without user sign-off is a contract violation.
2. **No Aggressive Alarms**:
   - Avoid creating high-priority notifications for informal social touchpoints.
3. **Preserve Human Nuance**:
   - Recognize polite decline phrases (e.g. *"改天吧"*, *"有机会再说"*) as non-actionable chatter, discarding them from the Signal Card.
