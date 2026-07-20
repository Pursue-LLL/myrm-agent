---
name: multi-agent-orchestration
description: >-
  Orchestrate complex tasks by delegating to specialized sub-agents. Manages task
  decomposition, parallel execution, result synthesis, and quality assurance across
  multiple expert roles.
version: 1.0.0
category: workflow
tags:
  - orchestration
  - multi-agent
  - delegation
  - parallel-execution
  - synthesis
allowed-tools: delegate_task_tool file_write_tool file_read_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Task Analysis — decompose the problem into expert-level subtasks"
    - "Phase 2: Expert Assignment — identify required expertise and assign to sub-agents"
    - "Phase 3: Parallel Execution — delegate subtasks with clear specifications"
    - "Phase 4: Result Integration — synthesize sub-agent outputs into a coherent result"
    - "Phase 5: Quality Check — verify consistency, completeness, and conflict resolution"
  potential_traps:
    - description: "Sub-agents producing conflicting conclusions without resolution"
      mitigation: "Define a conflict resolution protocol: compare evidence strength, escalate to user if unresolvable"
      severity: high
    - description: "Over-decomposition leading to coordination overhead exceeding the task complexity"
      mitigation: "Only delegate if the task genuinely benefits from multiple perspectives. Simple tasks should not be orchestrated."
      severity: medium
  verification_steps:
    - step_id: decomposition_valid
      description: "Subtasks collectively cover the entire original task with no gaps"
      validation_method: "Map each original requirement to at least one subtask"
      is_required: true
    - step_id: results_consistent
      description: "Sub-agent outputs don't contradict each other"
      validation_method: "Cross-check key findings and conclusions across all sub-agent results"
      is_required: true
  success_criteria: "Integrated result that is higher quality than any single-agent attempt"
  estimated_duration_seconds: 2400
---

# Multi-Agent Orchestration

## Overview

Some tasks benefit from multiple specialized perspectives working in parallel. This skill guides the orchestration of sub-agents for complex, multi-faceted tasks.

**When to use:** Tasks that genuinely require multiple areas of expertise (e.g., a technical migration that needs database, API, frontend, and DevOps expertise simultaneously).

**When NOT to use:** Simple tasks that a single agent can handle well. Orchestration has overhead — only use when the quality benefit justifies it.

## Phase 1: Task Analysis

### Decomposition Criteria

A task should be decomposed when:
- It spans 3+ distinct technical domains
- Different parts require fundamentally different expertise
- Parts can be worked on independently (parallelizable)
- The combined result is better than sequential work

### Decomposition Process

1. **Identify the core objective** — What is the final deliverable?
2. **Map required expertise** — What specialized knowledge is needed?
3. **Define subtask boundaries** — Each subtask should be self-contained
4. **Identify dependencies** — Which subtasks need outputs from others?
5. **Define interfaces** — What information passes between subtasks?

## Phase 2: Expert Assignment

### Expert Roles

Define each expert's scope clearly:

```
Expert: {Role Name}
Scope: {What this expert is responsible for}
Input: {What information they receive}
Output: {What they must deliver}
Constraints: {Quality requirements, format, boundaries}
```

### Common Expert Patterns

| Task Type | Recommended Experts |
|-----------|-------------------|
| Full-stack feature | Frontend + Backend + Database + Tests |
| System migration | Architecture + Data + Integration + Rollback |
| Security audit | Code Review + Penetration + Compliance + Remediation |
| Research report | Literature Review + Data Analysis + Domain Expert + Editor |

## Phase 3: Parallel Execution

Use `delegate_task_tool` to assign subtasks to sub-agents:

### Delegation Specification

Each delegation must include:

1. **Clear objective** — What specific output is expected
2. **Context** — Relevant background information
3. **Constraints** — Format requirements, quality standards
4. **Deadline indication** — Relative priority and urgency

### Execution Strategy

```
Independent tasks → Delegate in parallel
Dependent tasks → Sequential delegation (output of A feeds into B)
Review tasks → Delegate after all production tasks complete
```

## Phase 4: Result Integration

Once sub-agents complete:

1. **Collect all outputs** — Gather deliverables from each sub-agent
2. **Check completeness** — Does each output meet its specification?
3. **Identify overlaps** — Where do outputs cover the same ground?
4. **Resolve conflicts** — When experts disagree, evaluate evidence
5. **Synthesize** — Merge into a coherent final deliverable

### Conflict Resolution Protocol

When sub-agents produce conflicting conclusions:

1. Compare the evidence each provides
2. Check if they're answering slightly different questions
3. Determine if both perspectives are valid (complement, not conflict)
4. If genuinely conflicting, present both views with evidence to the user

## Phase 5: Quality Check

Before delivering the final result:

- [ ] All subtasks completed and outputs collected
- [ ] No contradictions between sub-agent outputs
- [ ] Final result covers the entire original objective
- [ ] Quality meets or exceeds single-agent baseline
- [ ] Result is coherent — reads as one unified deliverable, not stitched-together parts
