"""Delivers the completion guard's instruction with the next model request.

When the guard holds a draft back it routes the run to the model again and leaves the instruction in the turn's
guard state. This middleware appends that instruction after the message it follows (the held-back draft, or the
message before a draft that was taken out of the conversation), for that one request only: the instruction is
never stored in the conversation, so it cannot be approved, counted, traced or scanned as a tool call, and it
changes no earlier byte of the request (the prompt-cache prefix stays intact).

[INPUT]
- langchain.agents.middleware::AgentMiddleware, ModelRequest, ModelResponse (POS: LangChain model-call wrapper contract)
- agent.middlewares.completion.completion_guard.state::current_run_state (POS: the turn's pending instruction)

[OUTPUT]
- CompletionDirectiveMiddleware: appends the pending instruction after the message it follows

[POS]
Sits innermost among the middlewares that rewrite the request, so the memory and context middlewares that append to
the last user message keep appending to the user's own message, not to the instruction.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard.state import current_run_state


class CompletionDirectiveMiddleware(AgentMiddleware):
    """Appends the guard's pending instruction after the message it was written to follow."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        pending = current_run_state().pending_directive
        if pending is not None and request.messages and request.messages[-1].id == pending.anchor_id:
            request = request.override(messages=[*request.messages, HumanMessage(content=pending.text)])
        return await handler(request)


__all__ = ["CompletionDirectiveMiddleware"]
