"""Which model round a tool call belongs to.

[INPUT]
- langchain_core.messages::AIMessage (POS: the model response whose tool_calls a call came from)

[OUTPUT]
- model_round_id(): id shared by every tool call one model response issued

[POS]
Lets the loop guard count the rounds a run uses instead of the tool calls it makes: a model that
calls several tools at once spends one round, however many calls that round holds.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage


def model_round_id(state: object, tool_call_id: str) -> str | None:
    """Id of the model response that issued ``tool_call_id``; ``None`` when no response in ``state`` did.

    The calls of one response run side by side and all see the state as it was when they were issued,
    so they resolve to the same response however they are scheduled.
    """
    messages = state.get("messages") if isinstance(state, dict) else None
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if isinstance(message, AIMessage) and any(call["id"] == tool_call_id for call in message.tool_calls):
            return message.id or message.tool_calls[0]["id"]
    return None
