"""Skip of a clarification card over the API, and the evidence that it reached the agent.

[INPUT]
- none: pure functions over SSE events and stored chat messages

[OUTPUT]
- skip_resume_value: the resume value of a skip; it names the pause it answers
- open_clarification: the newest stored card of a chat, when it still waits for an answer
- pending_clarification_interrupt_id: the pause that card waits on
- sse_message_text: the assistant text of a stream
- continued_after_skip: whether a skip got the agent to continue

[POS]
Measurement ruler of the clarify-skip E2E. A skip that names no pause reaches nobody: the run ends in a bare
message_end, or the card is announced again. So a skip is judged by evidence of continuation, never by the stream
merely ending.
"""

from __future__ import annotations

from collections.abc import Sequence

# Wire key shared with the server: a resume value carrying it addresses one specific pause.
INTERRUPT_ID_KEY = "interruptId"


def skip_resume_value(interrupt_id: str) -> dict[str, object]:
    return {INTERRUPT_ID_KEY: interrupt_id}


def _stored_clarification(message: dict[str, object]) -> dict[str, object] | None:
    if message.get("role") != "assistant":
        return None
    for key in ("metadata", "extra_data"):
        container = message.get(key)
        if isinstance(container, dict):
            card = container.get("clarification")
            if isinstance(card, dict):
                return card
    return None


def open_clarification(messages: Sequence[object]) -> dict[str, object] | None:
    """The newest card of the chat when it is unanswered; None when the newest card is answered or there is none."""
    for message in reversed(messages):
        card = _stored_clarification(message) if isinstance(message, dict) else None
        if card is None:
            continue
        if card.get("answered") is False:
            return card
        if card.get("answered") is True:
            return None
    return None


def pending_clarification_interrupt_id(messages: Sequence[object]) -> str | None:
    """None when no card is open or the server stored the open card without an id."""
    card = open_clarification(messages)
    interrupt_id = card.get(INTERRUPT_ID_KEY) if card else None
    return interrupt_id if isinstance(interrupt_id, str) and interrupt_id else None


def sse_message_text(events: Sequence[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        data = event.get("data")
        if event.get("type") == "message" and isinstance(data, str):
            chunks.append(data)
    return "".join(chunks)


def continued_after_skip(events: Sequence[dict[str, object]]) -> bool:
    """A skip continued the agent when it answered in text and neither failed nor asked the question again."""
    kinds = {event.get("type") for event in events}
    return not kinds & {"error", "clarification_required"} and bool(
        sse_message_text(events).strip()
    )
