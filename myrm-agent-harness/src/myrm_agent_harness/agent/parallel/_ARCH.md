# parallel/

## Overview

Shared parallel subagent spawn path for `delegate_task_tool` (mode=batch|parallel) and Swarm Fission; reuses the same spawn metadata path as batch delegate.

Detailed design: see [sub_agents/SUB_AGENT_SYSTEM.md](../sub_agents/SUB_AGENT_SYSTEM.md) (parallel execution section).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Re-exports parallel runner and fission entrypoints. | — |
| `config.py` | Config | Default/cap for swarm fission concurrency. | — |
| `schemas.py` | Types | `ParallelTaskResults` resume contract. | — |
| `summary.py` | Core | Public `batch_summary` (with handover, evidence lineage and citation aggregation) / `inject_capacity_signal`. | — |
| `resume_compact.py` | Utility | Vault/truncate oversized resume payloads. | — |
| `runner.py` | Core | `run_parallel_task_requests` — concurrent `_delegate.coroutine`; children share the parent's workspace, a race returns the first success and cancels the rest. Each child runs inside `approvals_unanswerable()`: a child that needs a UI approval is declined with a readable reason and its paused thread is released. | — |
| `fission.py` | Core | `execute_swarm_fission` — parse interrupt payload `tasks[]`, resume dict. | — |

## Tests

| File | Role |
|------|------|
| `tests/agent/parallel/test_parallel_runner.py` | Runner batch results and race semantics (first success wins, losers cancelled, nothing merged) |

## Module Dependencies

- `agent/sub_agents/` — spawn/delegate implementation
- `agent/meta_tools/spawn_subagent/` — delegate_task_tool batch/parallel modes
