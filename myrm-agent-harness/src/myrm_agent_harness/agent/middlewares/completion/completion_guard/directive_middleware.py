"""Delivers the completion guard's instruction with the model requests that follow a hold-back.

When the guard holds a draft back it routes the run to the model again and leaves the instruction in the turn's
guard state. This middleware writes that instruction into the run's notice ledger behind the message it follows (the
held-back draft, or the message before a draft that was taken out of the conversation), and every request of the run
from then on carries it there unchanged. The instruction is never stored in the conversation, so it cannot be approved,
counted, traced or scanned as a tool call. No request changes a byte of the one before it: a reasoning block the
provider signed is valid only under the prompt it was written in, and the prompt-cache prefix stays intact.

[INPUT]
- langchain.agents.middleware::AgentMiddleware, ModelRequest, ModelResponse (POS: LangChain model-call wrapper contract)
- agent.middlewares._run_notices::NoticeLedger, last_stored_message, run_scope (POS: Request-local notices that keep their place and their text for the whole run.)
- agent.middlewares.completion.completion_guard.state::current_run_state (POS: the turn's pending instruction)

[OUTPUT]
- CompletionDirectiveMiddleware: places the pending instruction behind the message it follows

[POS]
Sits innermost among the middlewares that rewrite the request, so the memory and context middlewares that append to
the last user message keep appending to the user's own message, not to the instruction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from myrm_agent_harness.agent.middlewares._run_notices import NoticeLedger, last_stored_message, run_scope
from myrm_agent_harness.agent.middlewares.completion.completion_guard.state import current_run_state

_LEDGER_KEY = "completion_directive_notice_ledger"


class CompletionDirectiveMiddleware(AgentMiddleware):
    """Puts the guard's pending instruction behind the message it was written to follow, for the rest of the run."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        ledger = NoticeLedger.of(run_scope(request), _LEDGER_KEY)
        pending = current_run_state().pending_directive
        # Notices of the middlewares in front stand behind the stored messages without being part of the conversation,
        # so the message the instruction follows is the last one the graph stored.
        anchor = last_stored_message(request.messages)
        if pending is not None and anchor is not None and anchor.id == pending.anchor_id:
            ledger.record(anchor, pending.text)
        return await handler(request.override(messages=ledger.placed_in(request.messages)))


__all__ = ["CompletionDirectiveMiddleware"]
