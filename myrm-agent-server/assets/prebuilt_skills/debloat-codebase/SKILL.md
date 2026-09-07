---
name: debloat-codebase
description: "Autonomous multi-agent codebase slimming, dead code pruning, and behavior-preserving equivalence refactoring pipeline."
allowed-tools:
  - bash
  - file_read
  - file_write
  - file_str_replace
  - glob
  - grep
  - subagent_spawn
  - git_pr_create
---

# Codebase Slimming & Equivalence Refactor Protocol

When invoked via `/debloat-codebase` or when instructed to clean up and slim a repository, follow this 4-phase deterministic pipeline.

## Phase 1: Dependency Topology & Dead Code Discovery
1. Run AST dependency scanner to build the global symbol reference graph and detect 0-reference functions, classes, and isolated files.
2. Group identified dead code candidates by module boundary (e.g. `frontend/`, `server/api/`, `utils/`).
3. Assert that all public APIs in `__all__` or entrypoints are explicitly exempt from unreferenced deletion.

## Phase 2: Parallel Wave Subagent Delegation
1. Use `execute_dag_plan` or `run_alternatives` with `WorkspacePolicy.ISOLATED_COPY` (Git Worktree isolation).
2. Spawn dedicated subagents per module to prune unused imports, dead functions, and redundant wrappers in parallel.
3. Subagents must never cross module boundaries to avoid merge conflicts.

## Phase 3: Behavior Equivalence & Test Invariance Guard
1. In each isolated worktree, run existing unit and regression tests (`pytest`, `bun run test`).
2. If any test fails, analyze whether the failure is due to dynamic introspection or legitimate usage; if legitimate, rollback that specific deletion.
3. Merge verified clean worktree changes back into the target branch.

## Phase 4: Slimming Ledger & PR Generation
1. Calculate lines of code cut, file count reductions, and estimated token savings for future agent interactions.
2. Output a structured debloat report with exact diff statistics and test verification proofs.
