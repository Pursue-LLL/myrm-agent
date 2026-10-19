# live_transcript/

## Overview

Delegation transparency for subagents: a structured live transcript of what a delegated
subagent is doing, a crash-resilient ledger of delegations, a reasoning-effort governor, and
a smart-approvals gate for single commands.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports the emitter, ledger, governor, approvals gate and models. | — |
| transcript_emitter.py | Core | Emits human-readable structured telemetry for delegated subagents. | — |
| delegation_ledger.py | Core | Persistent delegation ledger — crash-resilient storage, status lifecycle, orphan detection. | — |
| reasoning_governor.py | Core | MoA reasoning-effort governor — allocates low / medium / max / ultra intensity and token budget. | — |
| smart_approvals.py | Core | Smart approvals gate — isolated single-command review, risk scoring, custom deny rules. | — |
| types.py | Core | Data types shared by the transcript, ledger, governor and approvals gate. | — |

## Key Dependencies

- `pydantic` (models)

## Key Design Decisions

- **The ledger survives a crash**: delegation state is persisted, so a restart can tell a lost
  delegation from a running one instead of losing track of both.
- **Reasoning effort is a budget, not a label**: the governor converts the chosen intensity into
  a token allocation, so "max" has a concrete cost.
- **Approvals are per command**: each command is reviewed in isolation, so approval of one
  command never implies approval of the next.
