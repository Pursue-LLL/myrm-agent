"""Delivers the completion guard's instruction with the next model request.

When the guard holds a draft back it routes the run to the model again and leaves the instruction in the turn's
guard state. This middleware appends that instruction after the draft, for that one request only: the instruction
is never stored in the conversation, so it cannot be approved, counted, traced or scanned as a tool call, and it
changes no earlier byte of the request (the prompt-cache prefix stays intact).

[INPUT]
- langchain.agents.middleware::AgentMiddleware, ModelRequest, ModelResponse (POS: LangChain model-call wrapper contract)
- agent.middlewares.completion.completion_guard_state::current_run_state (POS: the turn's pending instruction)

[OUTPUT]
- CompletionDirectiveMiddleware: appends the pending instruction after the held-back draft

[POS]
Sits innermost among the middlewares that rewrite the request, so the memory and context middlewares that append to
the last user message keep appending to the user's own message, not to the instruction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard_state import current_run_state


class CompletionDirectiveMiddleware(AgentMiddleware[Any, Any, Any]):
    """Appends the guard's pending instruction after the draft it held back."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        pending = current_run_state().pending_directive
        if pending is not None and request.messages:
            last = request.messages[-1]
            if isinstance(last, AIMessage) and last.id == pending.draft_id:
                request = request.override(messages=[*request.messages, HumanMessage(content=pending.text)])
        return await handler(request)


__all__ = ["CompletionDirectiveMiddleware"]
