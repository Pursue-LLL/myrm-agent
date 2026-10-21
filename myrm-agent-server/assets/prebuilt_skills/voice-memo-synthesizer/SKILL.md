---
name: voice-memo-synthesizer
description: >-
  Enterprise-grade voice memo and meeting recording synthesis workflow.
  Transforms spoken memos into structured meeting minutes artifacts, actionable
  kanban tasks with strict gating and idempotency, long-term memory facts, and
  standard UTF-8-SIG spreadsheet artifacts.
version: 1.0.0
category: productivity
tags:
  - voice
  - memo
  - meeting-minutes
  - kanban
  - memory
  - artifacts
  - spreadsheet
allowed-tools: file_write_tool kanban_add_task kanban_list_tasks memory_save_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Ingest & Deconstruct — transcribe or parse voice memo content into speakers, core agenda, and debate consensus"
    - "Phase 2: Meeting Minutes Artifact — output a structured Markdown document via file_write_tool and register as an interactive artifact"
    - "Phase 3: Actionable Kanban Dispatch — extract tasks passing Actionability Threshold and dispatch via kanban_add_task with idempotency_key"
    - "Phase 4: Knowledge & Memory Retention — persist long-term strategic decisions and key facts into memory via memory_save_tool"
    - "Phase 5: Tabular Data Export (Optional) — if financial, schedule, or quantitative items exist, execute Python script to produce utf-8-sig CSV/Excel"
  potential_traps:
    - description: "Creating trivial or low-value kanban tasks from casual chatter"
      mitigation: "Strict Actionability Threshold: require verb-noun structure, designated owner/context, and work estimate >= 30min with a tangible deliverable"
      severity: high
    - description: "Polluting wrong boards when target board_id is omitted"
      mitigation: "Enforce Board Resolution Protocol: query active board via kanban_list_tasks(limit=1); if absent, output markdown recommendations instead of throwing errors"
      severity: medium
    - description: "Duplicate task creation upon network retries or session resume"
      mitigation: "Compute deterministic idempotency_key = f'memo:{date_slug}:{task_slug}' for each kanban task"
      severity: high
    - description: "Garbled Chinese or non-ASCII characters when opening exported CSV in desktop Excel"
      mitigation: "Always specify encoding='utf-8-sig' when generating CSV artifacts in the Python execution sandbox"
      severity: medium
  verification_steps:
    - step_id: minutes_artifact_created
      description: "Structured meeting minutes Markdown file is written to docs/meetings/ and registered as an artifact"
      validation_method: "file_write_tool returns success and artifact is accessible in UI"
      is_required: true
    - step_id: kanban_tasks_dispatched
      description: "All high-confidence action items are created in the target kanban board with unique idempotency keys"
      validation_method: "kanban_add_task returns created or already_exists status without unhandled exceptions"
      is_required: false
    - step_id: memory_persisted
      description: "Crucial strategic decisions are permanently saved to long-term memory"
      validation_method: "memory_save_tool returns success acknowledgment"
      is_required: false
  success_criteria: "Spoken memo is completely transformed into structured minutes artifact, active kanban tasks, and long-term memory"
  estimated_duration_seconds: 300
---

# Voice Memo & Meeting Action Synthesizer

## Overview

Transform spontaneous voice memos, dictate recordings, and meeting transcripts into four-dimensional structured assets:
1. **Meeting Minutes Artifact** (Markdown documentation)
2. **Actionable Kanban Tasks** (Autonomous task dispatch with idempotency)
3. **Long-Term Memory Facts** (Knowledge retention for cross-session recall)
4. **Structured Spreadsheet Artifact** (Data analysis / timeline tables with UTF-8-SIG)

---

## Operating Protocol

### Phase 1: Semantic Deconstruction

Analyze the transcribed text or input memo across three distinct facets:
- **Core Agenda & Background**: What is the problem statement and context?
- **Decisions & Consensus**: What was agreed upon? (Exclude unresolved arguments)
- **Action Items**: What needs to be delivered, by whom, and when?

---

### Phase 2: Meeting Minutes Artifact (Markdown)

Always generate a clean, structured Markdown artifact using `file_write_tool`:

- **Target Path**: `docs/meetings/YYYY-MM-DD-{topic-slug}.md`
- **Required Sections**:
  1. `# Meeting Minutes: {Topic}`
  2. `**Date & Participants**`
  3. `## 1. Executive Summary`
  4. `## 2. Key Decisions & Agreements`
  5. `## 3. Action Items (Actionability Gated)`
  6. `## 4. Open Questions & Future Considerations`

The `file_write_tool` will automatically register the file with the system Artifact Registry and present it in the interactive right-hand artifact panel.

---

### Phase 3: Actionable Kanban Dispatch Protocol

To prevent task board pollution, enforce the **Actionability Threshold**:

#### Threshold Gating Rule
A mentioned item qualifies for `kanban_add_task` ONLY IF:
1. It has a clear **verb-object** goal (e.g., "Implement OAuth refresh token rotation").
2. It has an identifiable assignee or explicit owner role.
3. The estimated workload is **>= 30 minutes** with an inspectable deliverable.
4. *Non-qualifying items* (casual requests, minor favors, notes) MUST stay in the Markdown minutes as bullet points and MUST NOT be dispatched to the board.

#### Board Resolution Protocol
1. If the user specifies a board name or ID, target that board directly.
2. If omitted, call `kanban_list_tasks(limit=1)` to resolve the active/default board ID.
3. If no active board is found or available, gracefully present the formatted task list inside the Markdown minutes without crashing.

#### Deterministic Idempotency Key
Prevent duplicate tasks upon network retries:
```python
idempotency_key = f"memo:{date}:{slugify(task_title)}"
```

---

### Phase 4: Long-Term Knowledge & Memory Retention

For key organizational decisions, architecture agreements, or user constraints:
- Call `memory_save_tool` with:
  - `content`: Concise summary of the decision (e.g., "Architecture decision: JWT migration to Curve25519 finalized on 2026-09-05").
  - `memory_type`: `"knowledge"` or `"preference"`.

---

### Phase 5: Structured Tabular Data Export (Optional)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

When the meeting involves numerical budgeting, milestone matrices, or scheduling rosters:
- Use `bash_code_execute_tool` to generate a CSV or Excel artifact:
```python
# Mandatory encoding parameter for desktop Excel compatibility
df.to_csv("artifacts/schedule.csv", index=False, encoding="utf-8-sig")
```
- Report the generated table artifact path back to the conversation.
