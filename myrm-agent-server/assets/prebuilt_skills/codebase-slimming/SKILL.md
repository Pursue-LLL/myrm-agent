---
name: codebase-slimming
description: >-
  Autonomous codebase slimming, dead-code pruning, and equivalence refactoring pipeline.
  Employs concurrent subagent task orchestration with strict behavior invariance guards
  and automated test verification to cut dead abstractions while preserving 100% behavior.
version: 1.0.0
category: development
tags:
  - refactoring
  - anti-bloat
  - dead-code
  - optimization
  - subagent-orchestration
allowed-tools: bash_code_execute_tool file_read_tool grep_tool glob_tool
contract:
  steps:
    - "Phase 1: Topology & Dead Code Audit — trace unused exports, dead branches, and duplicate helpers"
    - "Phase 2: Dependency Partitioning — split tasks into non-conflicting waves (leaf to root)"
    - "Phase 3: Worktree-Isolated Refactoring — execute minimal changes per module in isolated worktrees"
    - "Phase 4: Equivalence Assertion & Verification — run full unit tests and assert 100% behavior invariance"
    - "Phase 5: Aggregation & Slimming Ledger — summarize lines cut, tokens saved, and verify test passes"
  potential_traps:
    - description: "Refactoring without running baseline tests before and after"
      mitigation: "Always establish passing baseline tests before any pruning"
      severity: high
    - description: "Simultaneous cross-cutting edits causing merge conflicts across waves"
      mitigation: "Strictly adhere to DAG wave ordering (leaf dependencies first)"
      severity: high
    - description: "Changing public contracts or behavioral semantics under the guise of slimming"
      mitigation: "Zero behavioral changes allowed; pure equivalence refactoring only"
      severity: high
  verification_steps:
    - step_id: baseline_pass
      description: "Existing test suite passes before starting refactoring"
      validation_method: "Run project test command and verify zero failures"
      is_required: true
    - step_id: equivalence_invariance
      description: "All existing tests pass with zero regressions after pruning"
      validation_method: "Re-run full test suite on refactored worktree"
      is_required: true
    - step_id: slimming_ledger
      description: "Outputs quantitative lines cut and modules simplified"
      validation_method: "Summary report includes diff stats and eliminated dead paths"
      is_required: true
  success_criteria: "Significant lines and token overhead eliminated with 100% passing tests and zero behavioral regressions"
  estimated_duration_seconds: 1800
---

# Codebase Slimming & Equivalence Refactoring

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## The Iron Rule of Equivalence Refactoring

```
ZERO BEHAVIORAL CHANGES — 100% TEST PASSING INVARIANCE
```

Codebase slimming is not rewriting business logic. It is eliminating dead code, removing unnecessary boilerplate, collapsing single-use wrappers, and pruning unreachable paths while ensuring every single existing test passes unconditionally.

## 5-Phase Refactoring Pipeline

### Phase 1: Topology & Dead Code Audit
1. **Unused Exports & Dead Files**:
   - Trace imports across the codebase using `grep_tool` and `glob_tool`.
   - Identify functions, classes, and types that have zero external references.
2. **Duplicate Helper Consolidation**:
   - Identify repeated utility patterns (e.g. repeated string normalization, duplicate JSON parsers).
   - Select the single canonical implementation.
3. **Over-Engineering & Dead Layers**:
   - Identify pass-through abstractions (interfaces or wrappers with only 1 implementation that add no runtime value).

### Phase 2: DAG Wave Partitioning
1. Group refactoring targets into dependency tiers:
   - **Wave 1 (Leaves)**: Standalone utilities, helpers, isolated models with zero downstream internal dependencies.
   - **Wave 2 (Middle Tier)**: Internal services and handlers depending only on Wave 1 components.
   - **Wave 3 (Roots / Public Facades)**: Top-level APIs and entry points.
2. Never refactor Wave N+1 before Wave N has verified and passed all tests.

### Phase 3: Worktree-Isolated Refactoring
1. Apply the **Necessity Ladder**:
   - Can this dead code simply be deleted? If yes, delete it.
   - Can this 30-line wrapper be replaced with a standard library one-liner? If yes, collapse it.
   - Can duplicate implementations be merged into the existing canonical helper? If yes, redirect callers.
2. Keep diffs focused and minimal per commit.

### Phase 4: Equivalence Assertion & Verification
1. **Pre-commit Gate**:
   - Run the relevant module tests immediately after editing.
2. **Full Regression Suite**:
   - Run the entire test suite (unit + integration).
   - If any test fails: investigate root cause immediately; if the failure was caused by an unintended behavior change, revert or adjust until tests pass 100%.

### Phase 5: Slimming Ledger & Summary
Output a structured report:
- **Lines of Code Cut**: Net deletions vs additions.
- **Dead Paths Eliminated**: Specific files or functions pruned.
- **Verification Status**: Test suite pass count and runtime.
- **Token Efficiency Gain**: Estimated context reduction for future agent sessions.
