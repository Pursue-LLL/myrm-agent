"""The scope in which model calls are memoised.

[INPUT]
- __future__
- contextlib::contextmanager
- contextvars::ContextVar
- dataclasses::dataclass, field
- typing::Any

[OUTPUT]
- LlmCallScope: the turn-scoped memo scope
- llm_call_scope: activate a scope for the duration of a block
- current_llm_call_scope: the scope in effect, or None
- enter_llm_call_scope / exit_llm_call_scope: explicit activation for callers that own the flow

[POS]
Framework-level scope for model-call memoisation. A scope names one turn (session + turn
identity), owns the counter of the calls made inside it, and holds the ledger the answers
are written to. The scope travels in a context variable, so the model adapter deep inside the
call stack can find it without every layer having to pass it down.

**No scope means no memoisation.** Every code path that does not open a scope behaves
exactly as before, which keeps the feature inert until a caller opts in.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from myrm_agent_harness.runtime.memo.memo_key import MemoKey, compute_memo_key
from myrm_agent_harness.runtime.memo.memo_ledger import MemoLedger
from myrm_agent_harness.runtime.memo.memo_types import MemoStatus

logger = logging.getLogger(__name__)


@dataclass
class LlmCallScope:
    """One turn's memo scope."""

    session_id: str
    turn_id: str
    ledger: MemoLedger
    _ordinal: int = field(default=0)

    def next_key(
        self,
        model: str,
        message_dicts: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
    ) -> MemoKey:
        """The identity of the next model call made inside this scope."""
        self._ordinal += 1
        return compute_memo_key(
            session_id=self.session_id,
            turn_id=self.turn_id,
            ordinal=self._ordinal,
            model=model,
            message_dicts=message_dicts,
            params=params,
        )


_current_scope: ContextVar[LlmCallScope | None] = ContextVar("myrm_llm_call_scope", default=None)


def current_llm_call_scope() -> LlmCallScope | None:
    """The scope in effect, or None when memoisation is not active."""
    return _current_scope.get()


def enter_llm_call_scope(scope: LlmCallScope | None) -> Token[object] | None:
    """Activate a scope and return the token that restores the previous one."""
    if scope is None:
        return None
    return _current_scope.set(scope)


def exit_llm_call_scope(token: Token[object] | None) -> None:
    """Restore the scope that was in effect before `enter_llm_call_scope`."""
    if token is not None:
        _current_scope.reset(token)


@contextmanager
def llm_call_scope(scope: LlmCallScope | None) -> Iterator[LlmCallScope | None]:
    """Activate a scope for the duration of the block."""
    token = enter_llm_call_scope(scope)
    try:
        yield scope
    finally:
        exit_llm_call_scope(token)


@dataclass(frozen=True)
class MemoAttempt:
    """The memo state of one model call attempt."""

    key: MemoKey | None
    response: dict[str, object] | None


def begin_memo_call(
    scope: LlmCallScope | None,
    model: str,
    message_dicts: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> MemoAttempt:
    """Look up the recorded answer for this call.

    Never raises: a ledger that is broken must not stop the agent from talking to the model,
    so a failure degrades to "no memo" and the call proceeds normally.
    """
    if scope is None:
        return MemoAttempt(None, None)
    try:
        key = scope.next_key(model, message_dicts, params)
        entry = scope.ledger.get(key.digest)
    except Exception:
        logger.warning("LLM memo lookup failed; continuing without memoisation.", exc_info=True)
        return MemoAttempt(None, None)
    if entry is not None and entry.status is MemoStatus.COMPLETED and entry.response is not None:
        return MemoAttempt(key, entry.response)
    return MemoAttempt(key, None)


def start_memo_call(scope: LlmCallScope | None, attempt: MemoAttempt, model: str) -> None:
    """Record that the call is about to be dispatched. Never raises."""
    if scope is None or attempt.key is None:
        return
    try:
        scope.ledger.record_started(attempt.key.digest, model)
    except Exception:
        logger.warning("LLM memo start write failed; the call will not be replayable.", exc_info=True)


def complete_memo_call(
    scope: LlmCallScope | None,
    attempt: MemoAttempt,
    model: str,
    response: dict[str, object],
) -> None:
    """Record the answer so a repeated call can read it back. Never raises."""
    if scope is None or attempt.key is None:
        return
    try:
        if not scope.ledger.record_completed(attempt.key.digest, model, response):
            logger.info("LLM memo: the answer is too large to memoise; a repeated call will be charged again.")
    except Exception:
        logger.warning("LLM memo write failed; the answer was not memoised.", exc_info=True)


def fail_memo_call(scope: LlmCallScope | None, attempt: MemoAttempt, model: str, error: str) -> None:
    """Record that the call failed. Never raises."""
    if scope is None or attempt.key is None:
        return
    try:
        scope.ledger.record_failed(attempt.key.digest, model, error)
    except Exception:
        logger.warning("LLM memo failure write failed.", exc_info=True)
