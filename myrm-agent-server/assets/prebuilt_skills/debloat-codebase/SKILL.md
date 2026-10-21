---
name: debloat-codebase
description: "Autonomous multi-agent codebase slimming, dead code pruning, and behavior-preserving equivalence refactoring pipeline."
allowed-tools: bash_code_execute_tool delegate_task_tool file_read_tool file_write_tool file_edit_tool glob_tool grep_tool
---

# Codebase Slimming & Equivalence Refactor Protocol

When invoked via `/debloat-codebase` or when instructed to clean up and slim a repository, follow this 4-phase deterministic pipeline.

## Phase 1: Dependency Topology & Dead Code Discovery
1. Run AST dependency scanner to build the global symbol reference graph and detect 0-reference functions, classes, and isolated files.
2. Group identified dead code candidates by module boundary (e.g. `frontend/`, `server/api/`, `utils/`).
3. Assert that all public APIs in `__all__` or entrypoints are explicitly exempt from unreferenced deletion.

## Phase 2: Parallel Wave Subagent Delegation
1. Call `delegate_task_tool` with `mode="batch"` and one task per module. Concurrent writing tasks run in isolated git worktrees (or isolated copies) and are merged back when the batch completes.
2. Each task prunes unused imports, dead functions, and redundant wrappers inside its own module only.
3. Subagents must never cross module boundaries to avoid merge conflicts.

## Phase 3: Behavior Equivalence & Test Invariance Guard
1. Each subagent runs the existing unit and regression tests (`pytest`, `bun run test`) for its module in its isolated workspace before reporting back.
2. If any test fails, analyze whether the failure is due to dynamic introspection or legitimate usage; if legitimate, rollback that specific deletion.
3. After the batch returns and the workspaces are merged, run the full test suite on the merged result and fix any integration failure.

## Phase 4: Slimming Ledger & PR Generation
1. Calculate lines of code cut, file count reductions, and estimated token savings for future agent interactions.
2. Output a structured debloat report with exact diff statistics and test verification proofs.

## Bash execution contract
Always provide a descriptive `reason` for executing bash commands (e.g. running AST scans, test runners, or git worktree operations). Never run untracked destructive shell operations without safety guards.
