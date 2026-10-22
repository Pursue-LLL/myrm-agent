"""The server side of model-call memoisation: one turn, one scope.

[INPUT]
- __future__
- collections.abc::AsyncIterable, AsyncIterator
- logging
- typing::Any
- myrm_agent_harness.runtime.memo.call_scope::LlmCallScope, llm_call_scope
- myrm_agent_harness.runtime.memo.memo_ledger::MemoLedger

[OUTPUT]
- build_memo_scope: the scope for one turn, or None when memoisation does not apply
- memo_scoped_stream: run an agent stream inside the turn's memo scope

[POS]
Business layer of the model-call memo. The harness owns the mechanism
(`myrm_agent_harness.runtime.memo`); the server decides *when* it applies: the turn
identity has to be the same for a turn and for the resume of that same turn, and only the
server knows it. Everything here is optional — without a turn identity or a ledger there is
no scope, and the agent behaves exactly as before.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from myrm_agent_harness.runtime.memo.call_scope import (
    LlmCallScope,
    enter_llm_call_scope,
    exit_llm_call_scope,
)
from myrm_agent_harness.runtime.memo.memo_ledger import MemoLedger

logger = logging.getLogger(__name__)


def build_memo_scope(params: Any) -> LlmCallScope | None:
    """The scope for one turn, or None when memoisation does not apply."""
    turn_identity = getattr(params, "turn_identity", None)
    ledger_path = getattr(params, "memo_ledger_path", None)
    session_id = getattr(params, "event_log_session_id", None) or getattr(params, "chat_id", None)
    if not turn_identity or not ledger_path or not session_id:
        return None
    try:
        ledger = MemoLedger(ledger_path)
    except Exception:
        logger.warning("LLM memo: the ledger could not be opened; continuing without memoisation.", exc_info=True)
        return None
    return LlmCallScope(session_id=str(session_id), turn_id=str(turn_identity), ledger=ledger)


async def memo_scoped_stream(
    stream: AsyncIterable[dict[str, object]],
    params: Any,
) -> AsyncIterator[dict[str, object]]:
    """Run an agent stream inside the turn's memo scope (a no-op when there is no scope).

    The token is scoped to one ``__anext__`` call instead of the whole generator. An async
    generator may be finalized (``aclose`` / cancellation / GC) by a different task than the
    one that advanced it, and ``ContextVar.reset`` rejects a token created in another
    ``Context``. Keeping set/reset in the same frame makes that cross-task close safe while
    the scope is still active for every model call the inner stream makes.
    """
    scope = build_memo_scope(params)
    if scope is None:
        async for chunk in stream:
            yield chunk
        return

    inner = stream.__aiter__()
    try:
        while True:
            token = enter_llm_call_scope(scope)
            try:
                chunk = await inner.__anext__()
            except StopAsyncIteration:
                return
            finally:
                exit_llm_call_scope(token)
            yield chunk
    finally:
        await inner.aclose()
