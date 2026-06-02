---
name: task-planning
description: >-
  Structured task decomposition and planning workflow. Breaks complex goals into
  actionable tasks with dependencies, priorities, time estimates, and milestones.
version: 1.0.0
category: productivity
tags:
  - planning
  - project-management
  - task-decomposition
  - prioritization
allowed-tools: file_write_tool file_read_tool kanban_add_task kanban_list_tasks kanban_board_summary kanban_add_dependency bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Goal Clarification — understand the objective, constraints, and success criteria"
    - "Phase 2: Decomposition — break into actionable tasks with clear deliverables"
    - "Phase 3: Dependency Mapping — identify task ordering and parallel opportunities"
    - "Phase 4: Estimation & Prioritization — assign time estimates and priority levels"
    - "Phase 5: Plan Output — produce a structured plan document or kanban board"
  potential_traps:
    - description: "Decomposing too finely, creating overhead without value"
      mitigation: "Each task should be 1-4 hours of work. Merge tiny tasks, split multi-day ones."
      severity: medium
    - description: "Missing dependencies that cause blocked tasks later"
      mitigation: "For each task, explicitly ask: what must be done before this can start?"
      severity: medium
  verification_steps:
    - step_id: goal_clear
      description: "Objective and success criteria are clearly defined"
      validation_method: "Can answer: what does 'done' look like?"
      is_required: true
    - step_id: tasks_actionable
      description: "Each task has a clear owner action and deliverable"
      validation_method: "Every task starts with a verb and has a measurable output"
      is_required: true
  success_criteria: "Complete plan with all tasks, dependencies, estimates, and priorities documented"
  estimated_duration_seconds: 900
---

# Task Planning

## Overview

Vague goals produce vague results. This workflow transforms ambiguous objectives into concrete, actionable task plans with clear dependencies and priorities.

## Phase 1: Goal Clarification

Before planning, establish clarity:

1. **What is the objective?** — State in one sentence
2. **What does success look like?** — Measurable criteria
3. **What are the constraints?** — Deadlines, resources, dependencies
4. **What is out of scope?** — Explicit exclusions prevent scope creep

If the goal is ambiguous, ask the user to clarify before proceeding.

## Phase 2: Decomposition

Break the goal into tasks. Each task must be:

- **Actionable** — Starts with a verb (implement, design, test, deploy)
- **Bounded** — 1-4 hours of focused work
- **Measurable** — Has a clear deliverable or completion criteria
- **Independent** — Minimize dependencies where possible

### Decomposition Strategy

1. **Top-down:** Goal → Milestones → Features → Tasks
2. **Group by system:** Frontend / Backend / Database / Infrastructure
3. **Identify unknowns:** Create "spike" or "research" tasks for uncertain areas

## Phase 3: Dependency Mapping

For each task, determine:

1. **What must be done before this?** (predecessors)
2. **What does this unblock?** (successors)
3. **Can this run in parallel with other tasks?**

Visualize dependencies:

```
[Design API] ──→ [Implement API] ──→ [Integration Test]
                                          ↑
[Design UI] ──→ [Implement UI] ────────────┘
```

Tasks without dependencies can start immediately (parallel).

## Phase 4: Estimation & Prioritization

### Time Estimation

For each task:
- **Optimistic:** Best case (no surprises)
- **Realistic:** Most likely (some friction)
- **Pessimistic:** Worst case (unexpected issues)

Use realistic estimates for planning. Add 20% buffer for unknowns.

### Priority Framework (Eisenhower)

| | Urgent | Not Urgent |
|---|---|---|
| **Important** | Do first | Schedule |
| **Not Important** | Delegate | Drop |

### Risk Assessment

Flag tasks with:
- External dependencies (APIs, approvals)
- Unknown technology or approach
- Critical path (blocking many other tasks)

## Phase 5: Plan Output

Produce one of:

### Option A: Markdown Plan

```markdown
## Project: {Name}
**Goal:** {One sentence}
**Timeline:** {Start} → {End}

### Milestones
1. [Date] Milestone 1: {Description}
2. [Date] Milestone 2: {Description}

### Tasks
| # | Task | Priority | Estimate | Depends On | Status |
|---|------|----------|----------|------------|--------|
| 1 | Design API schema | P0 | 2h | — | Ready |
| 2 | Implement API endpoints | P0 | 4h | #1 | Blocked |
```

### Option B: Kanban Board

Use `kanban_manage` to create tasks on the board:
- **Ready:** Tasks with no pending dependencies
- **Blocked:** Tasks waiting for dependencies
- Include priority labels and time estimates
