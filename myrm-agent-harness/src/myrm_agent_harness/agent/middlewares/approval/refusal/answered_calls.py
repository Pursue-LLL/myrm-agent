"""Which tool calls of a model response still need a verdict, and which of them stay in the AI message.

[INPUT]
- langchain_core.messages::AIMessage, BaseMessage, ToolCall, ToolMessage (POS: LangGraph message types)

[OUTPUT]
- answered_call_ids: ids of the calls of one AI message that a ToolMessage after it already answers
- kept_tool_calls: the tool calls an AI message keeps once some were approved, edited or refused

[POS]
LangGraph runs only the tool calls that have no ToolMessage, and the model reads a ToolMessage as the result of
its own call. A refused call therefore stays in the AI message, answered by an error ToolMessage, so the model
learns that it was refused and why. A call an earlier guard already answered is not put to a person again.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from langchain_core.messages import AIMessage, BaseMessage, ToolCall, ToolMessage


def answered_call_ids(messages: Sequence[BaseMessage], ai_message: AIMessage) -> set[str]:
    """Ids of the ToolMessages that follow *ai_message*, i.e. the calls an earlier guard already answered."""
    answered: set[str] = set()
    for message in reversed(messages):
        if message is ai_message or (message.id is not None and message.id == ai_message.id):
            break
        if isinstance(message, ToolMessage):
            answered.add(message.tool_call_id)
    return answered


def kept_tool_calls(
    original: Sequence[ToolCall], approved: Sequence[ToolCall], answered_ids: Collection[str]
) -> list[ToolCall]:
    """*original* with each approved call in its approved (possibly edited) form and each answered call kept.

    A call that is neither approved nor answered is dropped: it must not run without anyone having cleared it.
    """
    approved_by_id = {call.get("id"): call for call in approved}
    kept: list[ToolCall] = []
    for call in original:
        call_id = call.get("id")
        if call_id in approved_by_id:
            kept.append(approved_by_id[call_id])
        elif call_id in answered_ids:
            kept.append(call)
    return kept
