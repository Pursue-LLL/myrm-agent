"""Model-call memo ledger — one model call, one identity, one recorded answer.

[INPUT]
- __future__

[OUTPUT]
- MemoStatus: lifecycle state of a memoised model call
- MemoEntry: one recorded model call
- MemoKey: the identity of one model call inside one turn
- compute_memo_key: build a MemoKey from the call's inputs
- context_fingerprint: fingerprint of the request's messages and output-affecting parameters
- MemoLedger: persistent store of model-call outcomes
- LlmCallScope: the turn-scoped memo scope
- MemoAttempt: the memo state of one model call attempt
- begin_memo_call / start_memo_call / complete_memo_call / fail_memo_call: the call-side helpers (never raise)
- llm_call_scope: activate a scope for the duration of a block
- current_llm_call_scope: the scope in effect, or None
- enter_llm_call_scope / exit_llm_call_scope: explicit activation for callers that own the flow

[POS]
Framework-level memoisation of model calls. When a turn is interrupted and replayed, the
model would otherwise be paid for twice for the same question. This package gives the model
adapter a way to recognise "this is the same call as before" and read the recorded answer
back. It is business-agnostic: the caller supplies the turn identity and the ledger, and
nothing here knows about chats, providers or servers.
"""

from __future__ import annotations

from myrm_agent_harness.runtime.memo.call_scope import (
    LlmCallScope,
    MemoAttempt,
    begin_memo_call,
    complete_memo_call,
    current_llm_call_scope,
    enter_llm_call_scope,
    exit_llm_call_scope,
    fail_memo_call,
    llm_call_scope,
    start_memo_call,
)
from myrm_agent_harness.runtime.memo.memo_key import (
    MemoKey,
    compute_memo_key,
    context_fingerprint,
)
from myrm_agent_harness.runtime.memo.memo_ledger import MemoLedger
from myrm_agent_harness.runtime.memo.memo_types import MemoEntry, MemoStatus

__all__ = [
    "LlmCallScope",
    "MemoAttempt",
    "begin_memo_call",
    "complete_memo_call",
    "fail_memo_call",
    "start_memo_call",
    "MemoEntry",
    "MemoKey",
    "MemoLedger",
    "MemoStatus",
    "compute_memo_key",
    "context_fingerprint",
    "current_llm_call_scope",
    "enter_llm_call_scope",
    "exit_llm_call_scope",
    "llm_call_scope",
]
