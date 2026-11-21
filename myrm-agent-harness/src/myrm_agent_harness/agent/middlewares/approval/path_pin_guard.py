"""Run a file call only while it still opens the files it was judged on.

[INPUT]
- langchain.agents.middleware::wrap_tool_call, ToolCallRequest (POS: LangChain tool-call middleware hook, and the call being dispatched)
- agent.middlewares._session_context::get_workspace_root (POS: Middleware session context — shared ContextVars for the middleware chain.)
- agent.security.audit::record_decision (POS: The audit trail of security decisions.)
- .evaluation::path_moved, pin_of (POS: The files each file call was judged on, and the check that a call still opens them.)
- .refusal::DenialCause, refusal_answer (POS: The marked answer to a refused call.)

[OUTPUT]
- path_pin_guard: tool-call hook that answers a file call with a refusal when a path of it now leads to a file its verdict did not cover

[POS]
The calls of one model message are judged together before the first runs, and the calls that conflict then run one
after another. Registered inside ``ToolConflictGateMiddleware``, so every earlier call of the message that must run
first has finished: a link made by one is visible when the next is checked. The refused call never runs; the model
asks again and the new call is judged afresh. The person's own edit of a call is not held to the original paths.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares._session_context import get_workspace_root
from myrm_agent_harness.agent.security.audit import record_decision

from .evaluation import path_moved, pin_of
from .refusal import DenialCause, refusal_answer

_REFUSAL = (
    "Security Blocked: a path in this call now leads to a different file than the one it was judged on (a link or a "
    "rename changed it after the call was reviewed). Execution aborted to prevent opening a file nobody reviewed. "
    "Send the call again in a later message and it is judged afresh."
)


@wrap_tool_call
async def path_pin_guard(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
) -> ToolMessage | Command[object]:
    """Dispatch the call, unless a path of it now opens a file the verdict on it never covered."""
    call = request.tool_call
    call_id = call.get("id") or ""
    pin = pin_of(request.state, call_id) if call_id else None
    if pin is None or not path_moved(pin, call["name"], call["args"], get_workspace_root() or None):
        return await handler(request)
    record_decision(
        call["name"],
        "PATH_MOVED_REJECT",
        "A path of the call leads to a file its verdict did not cover; a link or rename changed it after the verdict",
        tool_call_id=call_id,
    )
    return refusal_answer(call, _REFUSAL, DenialCause.POLICY)
