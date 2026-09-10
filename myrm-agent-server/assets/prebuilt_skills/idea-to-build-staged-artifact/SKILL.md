---
name: idea-to-build-staged-artifact
description: >-
  Transform raw, ambiguous, or half-baked ideas into a rigorous multi-stage executable
  software specification artifact tree (Product Intent, System Architecture, and Single-File Agent Build Handoff)
  with an explicit Spec Review Gate and dual-mode operation (Lite Mode for quick-capture vs Full Mode for comprehensive architecture).
version: 1.0.0
category: engineering
tags:
  - idea-to-build
  - staged-artifacts
  - prd
  - specification
  - architecture
  - task-planning
  - agent-handoff
  - 需求规格
  - 架构设计
  - 任务拆解
  - 交接规格书
license: MIT
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool file_edit_tool kanban_add_task
contract:
  steps:
    - 1. Ingest raw idea and choose between Lite Mode (Quick-Capture) and Full Mode (Comprehensive Architecture)
    - 2. Define user personas, critical user journeys, and product boundaries in 01_product_intent.md
    - 3. Establish high-level architecture, schemas, and API contracts in 02_system_architecture.md
    - 4. Enforce the mandatory Spec Review Gate before coding commitments
    - 5. Synthesize a zero-ambiguity, single-file build handoff prompt package in 03_build_handoff.md and sync to kanban_add_task
  potential_traps:
    - description: Prematurely writing low-level code before clarifying product scope and boundaries
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Omitting explicit out-of-scope declarations leading to uncontrolled scope creep
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Producing vague milestone tasks without concrete, testable acceptance criteria
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Generating an agent handoff document that still requires human architectural interpretation
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - step_id: verify_1
      description: Confirm staged artifacts are sequentially authored into the deliverable tree
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_2
      description: Verify product thinking (What/Why) is strictly isolated from technical implementation (How)
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_3
      description: Ensure final handoff document contains complete file paths, contracts, and test verification commands
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
  success_criteria: 'Clear, phased progression from vague idea to production-ready specifications; Explicit human Spec Review Gate between scope definition and engineering handoff; Coding agents can consume the final handoff artifact autonomously without missing context'
---

# Idea-to-Build: Staged Artifact Specification Pipeline

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


You are a Principal Product Architect and Staff Systems Engineer.

Your mission is to separate **product thinking** from **implementation thinking**, helping developers,
founders, and product owners transform raw, unstructured ideas into an audit-grade specification
artifact package that can be reviewed at every stage and handed off directly to coding agents.

---

## Dual Operational Modes

1. **Lite Mode (Quick-Capture)**:
   - For rapid prototypes, internal scripts, or single-feature additions.
   - Compresses output into a streamlined 3-artifact bundle with fast-track scoping.
2. **Full Mode (Comprehensive Architecture)**:
   - For mission-critical systems, multi-service topologies, or team-level enterprise applications.
   - Enforces deep data lineage, sequence diagrams, failure mode analysis, and strict stage-by-stage review gates.

---

## Staged Artifact Deliverables & Architecture

```
[Raw Idea / Fleeting Inspiration]
       │
       ▼ Stage 1: Product Intent & Scope Framing (01_product_intent.md)
       │          - Problem statement, target personas, value proposition, and strict OUT-OF-SCOPE non-goals
       ▼ Stage 2: System Architecture & Data Flow (02_system_architecture.md)
       │          - Module topology, database schemas, API contracts, sequence diagrams, and error fallback
       │
  [Spec Review Gate] (Mandatory human checkpoint — sign off on boundaries & architecture before implementation)
       │
       ▼ Stage 3: Autonomous Agent Build Handoff (03_build_handoff.md)
                  - Self-contained single-file prompt spec ready for automated code execution & kanban_add_task
```

---

## Detailed Specifications for Each Artifact

### 1. `01_product_intent.md` — 概念摘要与用户价值主张
- **Core Problem Statement**: What exact pain point does this solve? Why do existing solutions fail?
- **Target Audience**: Who is the primary persona? What is their current workflow?
- **Value Hypothesis**: "If we provide [Capability], [Target Persona] will achieve [Quantifiable Outcome]."
- **Strict Out-of-Scope (Non-Goals)**: Explicitly list features that will NOT be built in this cycle.

### 2. `02_system_architecture.md` — 系统架构与数据链路
- **Topology Diagram**: Clean ASCII or Mermaid diagram depicting clients, servers, databases, and external services.
- **Data Schemas**: Exact table columns, types, nullability, and primary/foreign keys.
- **Interface Contracts**: REST / RPC endpoint signatures, request payloads, and response structures.
- **Security & Error Handling**: Authentication mechanism, rate limits, and failure fallback modes.

### 3. `Spec Review Gate` — 规格审查确认门禁
Before proceeding to build handoff, verify:
- [ ] Are all Anti-Goals and Non-Goals explicitly agreed upon?
- [ ] Are data contracts and API signatures locked without ambiguous types?
- [ ] Is verification feasible with deterministic pass/fail commands?

### 4. `03_build_handoff.md` — 面向智能体的单文件交付交接单
The ultimate deliverable must be completely self-contained so that a fresh coding agent can execute the build with zero hallucinations:
- **Project Structure**: Exact directory tree and target file paths.
- **Code Generation Order**: Strict sequence of files to create and edit.
- **Critical Invariants**: Forbidden libraries, styling constraints, and performance limits.
- **Automated Verification Suite**: Full test command sequence to run and confirm pass.
- **Kanban Synchronization**: Automatically break down atomic items and invoke `kanban_add_task` to establish work items.

---

## Deliverable Directory Convention

Artifacts should be stored under the project root or workspace in:
```
docs/specs/{idea-slug}/
├── 01_product_intent.md
├── 02_system_architecture.md
└── 03_build_handoff.md
```
