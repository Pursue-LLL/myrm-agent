"""Replay note of a channel turn, shown to the model after the user's message.

[INPUT]
- app.channels.reliability.inbound_journal::is_recovered (POS: whether a message was recovered from the journal after a restart)
- app.channels.types::InboundMessage (POS: the turn's inbound message)

[OUTPUT]
- attach_replay_notice(): the turn's query with the replay note appended; unchanged when the message is not a replay

[POS]
Step of the preamble beside the reference document. A message replayed after a restart is the one the user sent, so
without the note the model could not tell it from a new request and might repeat a step the interrupted run already
performed. The note rides on the live turn only: the persisted history keeps the user's message alone.
"""

from __future__ import annotations

from app.channels.reliability.inbound_journal import is_recovered
from app.channels.types import InboundMessage

_REPLAY_NOTICE = (
    "[System notice: this message reached the server before it restarted, so it may already have been partly handled. "
    "Before repeating a step that changes something outside this chat (sending a message, writing a file, running a "
    "command, calling an external service), check whether it was already done; then carry on with the request.]"
)


def attach_replay_notice(query: str | list[dict[str, object]], msg: InboundMessage) -> str | list[dict[str, object]]:
    """``query`` followed by the replay note when ``msg`` was replayed after a restart; unchanged otherwise.

    A multimodal query keeps its images: the note joins its text part, so the query has the shape it had without it.
    """
    if not is_recovered(msg):
        return query
    if isinstance(query, str):
        return f"{query}\n\n{_REPLAY_NOTICE}"
    for index, part in enumerate(query):
        text = part.get("text")
        if part.get("type") == "text" and isinstance(text, str):
            return [*query[:index], {**part, "text": f"{text}\n\n{_REPLAY_NOTICE}"}, *query[index + 1 :]]
    return [*query, {"type": "text", "text": _REPLAY_NOTICE}]
