---
name: idea-to-build-spec
description: >-
  Transforms ambiguous product ideas, user interview transcripts, or feature notes
  into staged, production-ready build specifications and actionable task worklists.
version: 1.0.0
category: engineering
tags:
  - product-management
  - specification
  - idea-to-build
  - requirements
  - staged-artifacts
allowed-tools: file_write_tool file_read_tool kanban_add_task kanban_list_tasks bash_code_execute_tool ask_question_tool
contract:
  steps:
    - "Phase 1: Idea Ingestion & Scope Classification (Lite Quick-Capture vs Full Staged Spec)"
    - "Phase 2: Product Thinking vs Implementation Thinking Separation"
    - "Phase 3: Staged Artifact Directory Structure Generation (.build-specs/)"
    - "Phase 4: Spec Review Gate & Risk Inventory"
    - "Phase 5: Single-File Agent Build Handoff (handoff.md & Kanban Task Breakdown)"
  potential_traps:
    - description: "Jumping directly into code architecture without clarifying the core user problem and non-goals"
      mitigation: "Always isolate Non-Goals and Core User Value before defining schemas or tech stack."
      severity: high
    - description: "Creating monolithic vague specifications that agent coders cannot execute sequentially"
      mitigation: "Enforce MECE staged artifacts and atomic tasks each <= 2 hours."
      severity: high
  verification_steps:
    - step_id: problem_statement_validated
      description: "Core problem statement, target persona, and non-goals are unambiguously stated"
      validation_method: "Checks that user pain point is quantified and at least 3 non-goals are listed"
      is_required: true
    - step_id: staged_artifacts_emitted
      description: "Structured directory .build-specs/ contains product, technical, and execution deliverables"
      validation_method: "Verify file presence of 01_problem_scope.md, 02_tech_spec.md, and 03_handoff.md"
      is_required: true
    - step_id: single_file_handoff_ready
      description: "Handoff file contains copy-pasteable execution contract for coder agents"
      validation_method: "Ensure handoff.md contains verification commands, file paths, and test invariants"
      is_required: true
  success_criteria: "Complete .build-specs/ folder created with staged specifications and a single-file agent handoff ready for execution"
  estimated_duration_seconds: 1200
---

# Idea to Build Specification Workflow (`idea-to-build-spec`)

## Overview

"I have an idea but don't want to write tedious docs."
This skill converts raw brain dumps, meeting transcripts, or whiteboard bullet points into a staged, production-grade build package that downstream Coder Agents or engineers can execute without ambiguity or hallucinated scope creep.

---

## Operating Philosophy: Product vs Implementation Separation

```
[Raw Idea Dump / Interview / Notes]
                │
                ▼
  ┌─────────────────────────────┐
  │ Phase 1: Ingestion & Scope  │ ──► Mode: Lite (Single PR) vs Full (Epic)
  └─────────────┬───────────────┘
                │
     ┌──────────┴──────────┐
     ▼                     ▼
┌──────────────┐     ┌──────────────┐
│   Product    │     │Implementation│
│   Thinking   │     │   Thinking   │
│ (Pain, Value,│     │(Stack, Arch, │
│  Non-Goals)  │     │ Contracts)   │
└──────┬───────┘     └──────┬───────┘
       │                    │
       └──────────┬─────────┘
                  │
                  ▼
  ┌─────────────────────────────┐
  │ Phase 3: Staged Artifacts   │ ──► Emits `.build-specs/{slug}/`
  └─────────────┬───────────────┘
                │
  ┌─────────────▼───────────────┐
  │ Phase 4: Spec Review Gate   │ ──► HITL / AskQuestion on ambiguities
  └─────────────┬───────────────┘
                │
  ┌─────────────▼───────────────┐
  │ Phase 5: Agent Build Handoff│ ──► Emits `03_handoff.md` + Kanban tasks
  └─────────────────────────────┘
```

---

## Phase 1: Ingestion & Scope Classification

Analyze the user's raw prompt or attached notes. Determine the target build mode:

1. **Lite Mode (Quick-Capture)**:
   - For focused single-screen features, micro-tools, or utility refactors (< 1 day build).
   - Generates a consolidated single-file spec: `.build-specs/{slug}-lite.md`.
2. **Full Mode (Staged Engineering Spec)**:
   - For multi-module features, stateful services, new protocols, or product workflows.
   - Generates the standard 3-stage artifact suite in `.build-specs/{slug}/`.

---

## Phase 2: Product Thinking vs Implementation Thinking

Do not mix user requirements with code implementation details. Separate them into two distinct cognitive layers:

### Layer A: Product Thinking
- **The Core Problem**: Who experiences the pain, when, and what is the current clumsy workaround?
- **User Journey**: Step 1 (Trigger) ➔ Step 2 (Action) ➔ Step 3 (Outcome & Reward).
- **Explicit Non-Goals**: Minimum 3 explicit boundaries that the implementation MUST NOT do.

### Layer B: Implementation Thinking
- **Architecture & Layering**: Where does the code live (Harness, Server, Frontend, CLI)?
- **Data Model & Contracts**: Pydantic / TypeScript interface definitions.
- **Security & Failure Invariants**: Rate limits, error boundaries, auth scopes, and offline fallback.

---

## Phase 3: Staged Artifact Directory Structure

In Full Mode, write the deliverables to `.build-specs/{slug}/`:

```
.build-specs/{slug}/
├── 01_problem_scope.md      # Persona, problem statement, user journeys, non-goals
├── 02_tech_spec.md          # Architecture, data schemas, API contracts, verification gates
└── 03_handoff.md            # Single-file execution contract for coding agents
```

### 1. `01_problem_scope.md` Structure
```markdown
# [Product Name] — Problem & Scope Definition

## 1. Problem Statement & Value Hypothesis
- **Target Persona**: [Who is this for]
- **Core Friction**: [What hurts today]
- **Value Hypothesis**: [Why this solves it]

## 2. Key User Journeys
1. **Happy Path**: User triggers X -> Sees Y -> Reaches Z.
2. **Edge / Recovery Path**: When condition A fails -> Fallback B is presented.

## 3. Explicit Non-Goals (Scope Boundary)
- [ ] Non-Goal 1: We will NOT build...
- [ ] Non-Goal 2: We will NOT support...
- [ ] Non-Goal 3: Out of scope for v1...
```

### 2. `02_tech_spec.md` Structure
```markdown
# [Product Name] — Technical Specification

## 1. Architecture & Component Placement
- **Frontend**: [Components, hooks, state stores]
- **Backend / Engine**: [Services, routes, database tables]
- **Cross-Cutting**: [Logging, metrics, i18n]

## 2. Data Models & Type Signatures
\`\`\`typescript
// Core Data Contracts
\`\`\`

## 3. Invariants & Safety Rails
- Performance budget, memory constraints, and zero-Any policy.
```

---

## Phase 4: Spec Review Gate (HITL Verification)

Before declaring the specification complete:
1. Scan for open architectural trade-offs (e.g., SQLite vs JSON file, local vs cloud).
2. If genuine product ambiguities exist, use `ask_question_tool` to present structured options with a recommended default.
3. Validate that all verification commands can run deterministically in sandbox.

---

## Phase 5: Single-File Agent Build Handoff (`03_handoff.md`)

The `03_handoff.md` file is the master contract designed specifically for autonomous Coder Agents. It MUST contain:

1. **Target Monorepo Paths**: Exact absolute/relative file paths to create or modify.
2. **Sequential Step-by-Step Task Checklist**: Each item atomic (<= 2 hours), verb-first.
3. **Verification Commands**: Exact test and lint commands to run (`bun run test ...`, `uv run pytest ...`).
4. **Acceptance Criteria**: Pass/Fail checklist.

If Kanban is enabled, call `kanban_add_task` to populate the Kanban board with the tasks defined in `03_handoff.md`.
