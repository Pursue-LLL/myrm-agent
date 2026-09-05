---
name: voice-corpus-review
description: >-
  Enterprise-grade voice corpus weekly digest and blocker review workflow.
  Aggregates multi-session voice memos, meeting notes, long-term memory, and
  active kanban board states across configurable time windows to synthesize
  executive progress conclusions, identify critical blockers, and generate
  review report artifacts.
version: 1.0.0
category: productivity
tags:
  - voice
  - corpus
  - review
  - weekly-digest
  - blockers
  - kanban
  - memory
  - artifacts
allowed-tools: memory_search_tool kanban_list_tasks file_write_tool
contract:
  steps:
    - "Phase 1: Multi-Corpus Ingestion — query memory_search_tool with corpus='all' across the review time window (default 7 days) to retrieve voice memos, meeting minutes, and architectural decisions"
    - "Phase 2: Kanban Blocker & Delivery Audit — call kanban_list_tasks to inspect blocked, running, and completed tasks across active boards"
    - "Phase 3: Root-Cause Synthesis & Risk Attribution — cross-reference meeting discussion items against actual kanban task blockers to uncover underlying causes and unresolved dependencies"
    - "Phase 4: Review Report Artifact Generation — write a comprehensive markdown review artifact via file_write_tool and register it in the workspace Artifact Portal"
    - "Phase 5: Executive Summary Presentation — output a concise, non-technical executive overview with direct jump links to the generated artifact and blocker tasks"
  potential_traps:
    - description: "Superficial keyword aggregation without causal link between voice discussions and board tasks"
      mitigation: "Cross-reference protocol: attribute every blocker to specific meeting context, responsible owner, and blocked kanban task ID"
      severity: high
    - description: "Token explosion caused by unbounded historical memory dumps"
      mitigation: "Strict temporal bounding: default query time window to since='7d' or explicit user date range, limiting retrieval results"
      severity: medium
    - description: "Failing gracefully when kanban boards or memory records are sparse"
      mitigation: "Graceful Fallback: if kanban returns no tasks or memory search returns few items, clearly state coverage scope in the generated report instead of throwing errors"
      severity: low
  verification_steps:
    - step_id: memory_corpus_queried
      description: "memory_search_tool is queried with corpus='all' and appropriate query keywords"
      validation_method: "Tool returns semantic memory facts and session records"
      is_required: true
    - step_id: kanban_tasks_inspected
      description: "kanban_list_tasks is invoked to retrieve task statuses (blocked, in-progress, completed)"
      validation_method: "Tool returns list of tasks or empty state handled gracefully"
      is_required: false
    - step_id: review_artifact_written
      description: "Review report markdown artifact is written under docs/reviews/ and registered in workspace"
      validation_method: "file_write_tool succeeds and returns target file path"
      is_required: true
  success_criteria: "Multi-session voice recordings and meeting inputs are aggregated into a four-pillar weekly review report artifact with attributed blockers and actionable next steps"
  estimated_duration_seconds: 180
---

# Voice Corpus Weekly Digest & Blocker Review

## Overview

Synthesizes fragmented voice memos, meeting recordings, architectural decisions, and active task board realities across an entire review cycle (typically 7 days) into a structured, executive-grade review report:
1. **Executive Progress & Key Takeaways**: High-level achievements and strategic agreements reached across meetings.
2. **Critical Blockers & Risk Attribution**: Unresolved bottlenecks, root causes, and blocked Kanban items.
3. **Delivery vs. Backlog Delta**: Contrast between planned commitments and actual task status.
4. **Actionable Next Steps & Priorities**: Concrete roadmap recommendations for the upcoming cycle.

---

## Operating Protocol

### Phase 1: Multi-Corpus Semantic Retrieval

Retrieve voice records, meeting transcripts, and long-term memory facts using `memory_search_tool`:
- **Corpus Selection**: Set `corpus="all"` to simultaneously search long-term memory, team wiki entries, and recent conversation history.
- **Search Queries**: Execute targeted queries covering:
  - `"本周会议 核心决议 需求评审 架构方案 weekly decisions meeting"`
  - `"阻碍 风险 依赖未决 技术难点 瓶颈 blockers risks dependencies"`
- **Temporal Bounding**: Focus context extraction on the designated review cycle (default: past 7 calendar days).

---

### Phase 2: Kanban Reality Cross-Audit

Cross-verify conversational commitments against ground-truth board execution state using `kanban_list_tasks`:
1. Call `kanban_list_tasks(status_filter="blocked")` to obtain all currently blocked items.
2. Call `kanban_list_tasks(status_filter="completed", limit=20)` to capture completed deliverables.
3. Inspect task titles, descriptions, and blocker reasons to correlate with meeting deliberations.

---

### Phase 3: Blocker Attribution & Root-Cause Analysis

For each identified blocker or stalled milestone:
- **Correlate Context**: Connect the stalled board task with the specific meeting or voice memo where the dependency was introduced.
- **Identify Blocker Type**: Categorize as `External Dependency`, `Technical Uncertainty`, `Resource Bottleneck`, or `Requirement Ambiguity`.
- **Assign Accountability**: Document the designated owner and expected unblocking date.

---

### Phase 4: Review Report Artifact Generation

Generate a comprehensive Markdown report artifact using `file_write_tool`:

- **Target Path**: `docs/reviews/YYYY-W{week_number}-weekly-review.md` (e.g. `docs/reviews/2026-W36-weekly-review.md`)
- **Required Structure**:
  1. `# Weekly Work Digest & Blocker Review (YYYY-W{WW})`
  2. `**Review Period**: YYYY-MM-DD ~ YYYY-MM-DD | **Sources**: N Meeting Recordings & Kanban Audits`
  3. `## 1. Executive Summary & Key Milestones`
  4. `## 2. Core Decisions & Consensus Reached`
  5. `## 3. Critical Blockers & Root-Cause Attribution Table`
     - Columns: `| Task / Item | Severity | Root Cause & Context | Responsible Owner | Recommended Next Action |`
  6. `## 4. Delivery Status vs. Board Realities`
  7. `## 5. Next Week Immediate Priorities`

`file_write_tool` will automatically register the file with the Artifact Registry, opening it in the interactive right-hand artifact pane for the user.

---

### Phase 5: Clean User Presentation

In the conversational output:
- Provide a crisp 3-paragraph executive overview.
- Highlight the **Top 3 Blockers** that require immediate human decision-making.
- Provide the relative path to the generated review artifact for 1-click inspection.
