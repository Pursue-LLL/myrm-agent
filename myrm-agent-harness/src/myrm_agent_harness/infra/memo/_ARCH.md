# memo/

## Overview
Model-call memo ledger — one model call, one identity, one recorded answer.

A turn that is interrupted and replayed would otherwise pay for the model twice for the same
question. This package lets the model adapter recognise "this is the same call as before" and
read the recorded answer back instead of calling the model again.

The identity of a call has three parts that must not be conflated:

- **who** — the session plus the **turn identity**, which the caller supplies because only
  the caller knows it: it must be identical for a turn and for the resume of that same turn,
  and different between two different turns;
- **which call** — the ordinal inside that turn;
- **what was asked** — the model identity plus a fingerprint of the request. The model
  identity belongs in the key because a failover swaps the model mid-turn: without it the
  first model's answer would be handed back as the second model's answer.

A call is recorded *before* it is dispatched (`started`) and its answer is written
afterwards (`completed`). A row left at `started` means the outcome is unknown — the call is
retried, because the model may or may not have been billed. Only `completed` is replayed.

**No scope means no memoisation**: every code path that does not open a scope behaves exactly
as before.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Model-call memo ledger facade. | — |
| `memo_types.py` | Config | `MemoStatus` lifecycle enum and the `MemoEntry` record. | ✅ |
| `memo_key.py` | Core | `MemoKey`, `compute_memo_key` and `context_fingerprint` — the identity of one model call. | ✅ |
| `memo_ledger.py` | Core | `MemoLedger` — SQLite store of model-call outcomes, written before dispatch and completed after. | ✅ |
| `call_scope.py` | Core | `LlmCallScope` and the context-variable plumbing that carries a turn's scope to the model adapter. | ✅ |

## Key Dependencies
- `runtime/memo` has no dependency on `agent`, `toolkits` or `server`; it is pure framework
  infrastructure.
