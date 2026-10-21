---
name: idea-to-build
description: >-
  Transform fleeting product ideas and developer concepts into audit-grade, staged build specifications
  and single-file agent handoff artifacts without upfront manual documentation overhead.
  Enforces separation of product thinking from implementation thinking via Lite quick-capture
  and Full 5-stage specification pipelines.
version: 1.0.0
category: engineering
tags:
  - idea-to-build
  - staged-artifacts
  - spec-review-gate
  - build-handoff
  - product-spec
  - task-breakdown
  - 灵感构建
  - 规格门禁
allowed-tools: file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - 1. Mode Selection & Intent Capture (Select Lite quick-capture or Full staged specification)
    - 2. Staged Artifact Synthesis (Generate 01-intent, 02-functional, 03-architecture, 04-tasks, 05-handoff)
    - 3. Spec Review Gate Verification (Validate non-goals, measurable criteria, and scope boundaries)
    - 4. Single-File Agent Build Handoff (Emit standalone executable build prompt contract for downstream coding agents)
  potential_traps:
    - description: Conflating product intent with coding implementation details prematurely
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Omitting explicit Non-Goals leading to scope creep and bloated agent implementations
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Generating untestable, vague acceptance criteria instead of verifiable physical assertions
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Providing fragmented instructions rather than a self-contained single-file handoff contract
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - step_id: verify_1
      description: Confirm all 5 staged spec artifacts exist or Lite contract is complete
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_2
      description: Verify Spec Review Gate passes all 3 mandatory checks (Non-Goals, Acceptance Criteria, Separation)
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_3
      description: Ensure 05-agent-build-handoff contains exact file paths, constraints, and smoke commands
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
  success_criteria: 'Turnkey, audit-grade build specification ready for immediate zero-ambiguity agent execution'
---

# Idea-to-Build Staged Artifact Pipeline (从灵感到构建：分阶段规格工件流水线)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

A dedicated skill for solo builders, product managers, and software architects to transform raw, unformatted ideas
into structured, build-ready specifications and single-file agent execution contracts.

The fundamental design axiom is:
**"Separate Product Thinking from Implementation Thinking"** (将产品/业务思考与工程实现思考严格分阶段解耦)。

It prevents the common pitfall where AI coding agents jump straight into generating code on ambiguous prompts,
resulting in architecture regressions, hallucinated features, and unmaintainable technical debt.

---

## Dual Pipeline Modes (双阶流水线模式)

Depending on project scope and velocity, select between two operational modes:

### Mode A: Lite Quick-Capture (轻量敏捷捕获)
For micro-tools, single utility scripts, UI tweaks, or rapid hacks (< 1 day build):
- **Output Artifact**: `docs/staged-specs/{idea-slug}/idea-lite.md`
- **Core Sections**:
  1. **Problem Statement**: 2-3 sentences defining the exact user friction.
  2. **Core Feature**: The minimal viable mechanism solving the friction.
  3. **Strict Non-Goals**: Explicit boundaries on what NOT to build.
  4. **Single-Shot Build Prompt**: Self-contained agent instructions with input/output contracts.

### Mode B: Full 5-Stage Staged Specification (生产级五阶规格流水线)
For end-to-end applications, multi-component services, or core features:
- **Output Directory**: `docs/staged-specs/{idea-slug}/`
  ```
  docs/staged-specs/{idea-slug}/
  ├── 01-product-intent.md       # Problem, Target Persona, Invariants & Non-Goals
  ├── 02-functional-spec.md      # User Stories, State Machines, UI Wireframes & Flows
  ├── 03-tech-architecture.md    # Tech Stack, DB Schema, API Contracts, Security Gates
  ├── 04-task-breakdown.md       # P0/P1/P2 Atomic Actionable Tasks with Acceptance Checks
  └── 05-agent-build-handoff.md  # Self-contained single-file execution blueprint for coding agent
  ```

---

## The 5 Staged Artifact Specifications

### 01. Product Intent (`01-product-intent.md`)
- **Problem Statement**: The verifiable friction or inefficiency.
- **Target Audience / Persona**: Primary users and operational context.
- **Value Metric**: How success is objectively measured (e.g. latency reduced by 50%, 0 manual steps).
- **Hard Non-Goals**: The list of tempting features explicitly out of scope for this version.

### 02. Functional Spec (`02-functional-spec.md`)
- **User Journeys**: Step-by-step interaction narrative.
- **Input / Output Boundary**: Exact data payload structures ingested and produced.
- **UI / UX State Machine**: Loading, Empty, Populated, Error, and Retry states.

### 03. Technical Architecture (`03-tech-architecture.md`)
- **Tech Stack Selection**: Runtime, framework, and database rationale.
- **Data Model & Schema**: Tables, indexes, and migrations.
- **API Endpoints**: REST / GraphQL / RPC schemas with error codes.
- **Hard Architectural Invariants**: Security rules, concurrency limits, and sandbox boundaries.

### 04. Task Breakdown (`04-task-breakdown.md`)
- **P0 Core Milestones**: The minimal verifiable path to working software.
- **P1 Edge Cases & Polish**: Hardening, error handling, and performance tuning.
- **Kanban / Todo Compatibility**: Formatted directly for ingestion by `task-planning` and Kanban orchestrators.

### 05. Agent Build Handoff (`05-agent-build-handoff.md`)
- **Single-File Execution Blueprint**: Everything a downstream coding agent needs in one self-contained document.
- **File System Targets**: Explicit paths to create/modify.
- **Testing & Verification Commands**: Exact terminal commands to assert build correctness.

---

## Spec Review Gate (规格审核门禁)

Before handing off `05-agent-build-handoff.md` to any coding agent, the specification MUST pass this 3-point checklist:

1. **Non-Goals Gate**: Are there at least 2 explicit Non-Goals preventing scope creep?
2. **Acceptance Criteria Gate**: Can every task in `04-task-breakdown.md` be verified deterministically via automated tests or smoke commands?
3. **Decoupling Gate**: Is product intent completely decoupled from temporary implementation details?
