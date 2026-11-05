"""The assistant reply an ``updates`` chunk delivers, kept or not

[INPUT]
- langchain_core.messages::AIMessage (POS: LangChain core message type)

[OUTPUT]
- latest_model_reply(): The last AIMessage an ``updates`` chunk carries, including an empty one that ``collected_messages`` leaves out

[POS]
The run's final reply as the turn-end recovery handlers judge it. ``collected_messages`` holds what can be re-sent;
a reply with no text, no reasoning text and no tool call is not among it, yet it is exactly what an empty-response or
reasoning-cut recovery has to see.
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.messages import AIMessage


def latest_model_reply(update: Mapping[str, object]) -> AIMessage | None:
    """Return the last AIMessage in an ``updates`` chunk, or None when the chunk carries none."""
    reply: AIMessage | None = None
    for node_output in update.values():
        if not isinstance(node_output, Mapping):
            continue
        messages = node_output.get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if isinstance(message, AIMessage):
                reply = message
    return reply
