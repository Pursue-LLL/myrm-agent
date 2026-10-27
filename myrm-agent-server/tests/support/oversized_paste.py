"""Texts sized from the limits that park a text, so a test names the limit and not a number.

The text of a person is parked from ``USER_TEXT_LIMITS``; a document a messaging channel attaches is parked from the
lower harness defaults. A text between the two stays in the prompt when a person sends it and is parked as a document.
"""

from __future__ import annotations

from myrm_agent_harness.agent.context_guard import ContextGuardConfig

from app.services.chat.context_bomb_guard import USER_TEXT_LIMITS


def paste_over_the_limit(line: str = "X") -> str:
    """Repeats of ``line``, just past the size from which the text of a person is parked."""
    return line * (USER_TEXT_LIMITS.max_message_chars // len(line) + 1)


def paste_between_the_limits(line: str = "X") -> str:
    """Repeats of ``line``, past the harness default (a channel document is parked) yet within a person's limit."""
    return line * (ContextGuardConfig().max_message_chars // len(line) + 1)
