"""Registry of the answers the installed stack reads differently from the previous one, each with its reason.

[INPUT]
- golden_compare::Allowed (POS: one entry: the facts that changed, with their new values, and why they are right)

[OUTPUT]
- ANSWER_ALLOWED: the recorded answers whose message changed

[POS]
An answer is read once into the message the agent acts on: text, tool calls, finish reason, token counts. An entry
exists only where the new message is the one the agent should act on; the reason says why. ``test_golden_answers``
fails on a changed message with no entry, on an entry whose facts differ from what happens now, and on an entry whose
case no longer differs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .golden_compare import Allowed

ANSWER_ALLOWED: Final[Mapping[str, Allowed]] = {
    "anthropic.server_tool": Allowed(
        {"tool_calls": []},
        "A tool the provider ran itself (server_tool_use, its result sits in the same message) is not a call for the "
        "agent to execute; the previous stack handed it over as a client tool call.",
    ),
    **{
        f"gemini.finish_{reason}": Allowed(
            {"content": "x"},
            "The text a blocked candidate carries is kept, and the finish reason still says content_filter; the "
            "previous stack dropped the text.",
        )
        for reason in ("BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION", "SAFETY")
    },
    "gemini.finish_OTHER": Allowed(
        {"finish": "stop"},
        "OTHER is a stop for an unstated reason, not a safety filter: reporting content_filter would suppress the "
        "turn's tool calls and tell the user a safety filter fired (the product's safety sets do not list OTHER).",
    ),
    "gemini.tools_thought_signature": Allowed(
        {"tool_id_thought": True},
        "The thought signature of a function call travels in the tool-call id (<id>__thought__<signature>), the one "
        "field every layer above keeps verbatim; the previous stack carried it in a side field of the tool call.",
    ),
    "openai.list_content": Allowed(
        {
            "outcome": "returned",
            "content": "part",
            "tool_calls": [],
            "tool_id_thought": False,
            "invalid_tool_calls": 0,
            "finish": "stop",
            "in": 5,
            "out": 2,
            "total": 7,
            "thinking_blocks": 0,
        },
        "A gateway that sends the message content as typed parts is read as its text; the previous stack raised.",
    ),
}
