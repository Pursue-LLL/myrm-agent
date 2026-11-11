"""Canary middleware.

Hands the session canary instruction to the model as an independent SystemMessage behind the user's input, so
the main System Prompt carries no per-session text.

Why not in the System Prompt: a provider caches a prompt as a prefix, and the random token ends the prefix it
shares with every other session at the token. The system prompt and the tool block behind it are then paid for
in full on the first call of every session and of every turn, although their bytes never change.

Placement:
    State merges a returned message by appending it, so the instruction lands behind the latest user message
    on the first model call of a thread and stays there. A thread that already carries a canary instruction,
    whichever token it holds, keeps it: the history behind it stays a stable prefix from turn to turn, and the
    guardrail checks the model's output for every token the history carries.

[INPUT]
- agent.security.detection.canary_guard::build_canary_instruction, instruction_canaries (POS: Output-side injection detector. Deterministic canary token for prompt injection success detection.)
- agent.middlewares._session_context::get_canary_token (POS: Middleware session context — shared ContextVars for the middleware chain.)
- core.message_origin::runtime_system_message (POS: Marks the instruction as the runtime's, so models that only advise are not shown the token.)

[OUTPUT]
- CanaryMiddleware: Middleware to add the canary instruction as a SystemMessage once per thread.
- carried_canaries: the canary tokens the system messages of a history carry.

[POS]
Canary middleware.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares._session_context import get_canary_token
from myrm_agent_harness.agent.security.detection.canary_guard import build_canary_instruction, instruction_canaries
from myrm_agent_harness.core.message_origin import runtime_system_message


def carried_canaries(messages: Sequence[BaseMessage]) -> list[str]:
    """The canary tokens the system messages carry; other roles cannot plant one."""
    return [
        token
        for message in messages
        if isinstance(message, SystemMessage) and isinstance(message.content, str)
        for token in instruction_canaries(message.content)
    ]


class CanaryMiddleware(AgentMiddleware):
    """Middleware to add the canary instruction as a SystemMessage once per thread."""

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Sequence[BaseMessage]] | None:
        canary = get_canary_token()
        messages = state.get("messages", [])
        if not canary or not messages or carried_canaries(messages):
            return None
        return {"messages": [runtime_system_message(build_canary_instruction(canary))]}
