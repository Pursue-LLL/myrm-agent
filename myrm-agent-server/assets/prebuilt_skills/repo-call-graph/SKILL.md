---
name: repo-call-graph
description: >-
  Deterministic code call graph navigator and impact analyzer. Provides 8 exact
  AST-level navigation tools (resolve, definition, callers, callees, implementors,
  overrides, importers, tests_reaching) and single-file incremental reingest.
  Replaces grep guesswork with 100% accurate symbol references and test blast radius.
version: 1.0.0
category: development
tags:
  - code-intelligence
  - call-graph
  - ast
  - refactoring
  - impact-analysis
allowed-tools: bash_code_execute_tool file_read_tool grep_tool
contract:
  steps:
    - "Phase 1: Index — run code graph scan or ensure the repository call graph is built"
    - "Phase 2: Resolve — resolve target symbols or file:line to exact qualified names"
    - "Phase 3: Trace — query callers, callees, or implementors to map the dependency tree"
    - "Phase 4: Blast Radius — call tests_reaching to determine affected test suites before editing"
    - "Phase 5: Validate — run only affected tests to verify changes with minimum latency"
  potential_traps:
    - description: "Using plain text grep when exact AST references are required"
      mitigation: "Always prefer callers() or definition() over grep for symbol tracing"
      severity: medium
    - description: "Forgetting to reingest modified files during multi-step refactoring"
      mitigation: "Trigger reingest_file after modifying functions or class definitions"
      severity: low
  verification_steps:
    - step_id: exact_callers_identified
      description: "All genuine call sites were verified using AST call graph"
      validation_method: "Inspect caller file paths and line numbers returned by the graph store"
      is_required: true
    - step_id: reaching_tests_executed
      description: "Tests reaching the modified code were executed"
      validation_method: "Verification test output confirms reaching tests passed"
      is_required: true
  success_criteria: "Complete symbol call chain identified and verified with zero hallucinated references"
  estimated_duration_seconds: 600
---

# Repo Call Graph AST Navigator

Deterministic AST-level code navigation for Python and TypeScript/JavaScript.

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## When to Use

1. **Refactoring Functions or Methods**: Find all genuine callers and their call sites before changing signatures.
2. **Impact Analysis & Blast Radius**: Trace which unit or integration tests directly or indirectly execute a modified block (`tests_reaching`).
3. **Class Hierarchy Navigation**: Find all subclasses or interface implementations (`implementors`).
4. **Module Dependency Tracing**: Find all modules importing a target symbol (`importers`).

## Available Deterministic Operations

The skill executes through python script invocation against `app.services.code_graph`:

- `python -m app.services.code_graph.cli resolve --target <symbol_or_path:line>`
- `python -m app.services.code_graph.cli callers --callee <qualified_name>`
- `python -m app.services.code_graph.cli callees --caller <qualified_name>`
- `python -m app.services.code_graph.cli definition --symbol <qualified_name>`
- `python -m app.services.code_graph.cli implementors --type <super_type>`
- `python -m app.services.code_graph.cli importers --module <module_name>`
- `python -m app.services.code_graph.cli tests_reaching --target <qualified_name>`
- `python -m app.services.code_graph.cli reingest --file <rel_file_path>`

Always check `tests_reaching` before refactoring core shared functions.
