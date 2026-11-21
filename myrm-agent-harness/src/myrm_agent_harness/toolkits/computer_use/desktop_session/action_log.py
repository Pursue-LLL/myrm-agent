"""Structured log lines of the desktop tools: fixed words and numbers, never what the screen or the model said.

[INPUT]
- types::DesktopInteractAction (POS: the closed verb vocabulary of desktop_interact)

[OUTPUT]
- InteractOutcome: how one desktop_interact call ended
- InteractTrace: records the path of one desktop_interact call and writes its one log line when the call ends
- CaptureRefusal, log_capture_refused: the log line of a vision screenshot the entry refused

[POS]
The measurement of how the desktop tools are used: which verbs are called, how often the native route does not
deliver, how often the coordinate fallback or the approval re-read is needed, how often a screenshot is refused.
A line carries no element name, text, value, application or window title, and the verb is read from a fixed
vocabulary, so a caller that passes anything else cannot put text in the line.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from types import TracebackType
from typing import Literal, Self, get_args

from myrm_agent_harness.toolkits.computer_use.types import DesktopInteractAction

logger = logging.getLogger(__name__)

_VERBS: frozenset[str] = frozenset(get_args(DesktopInteractAction))
_OTHER_VERB = "other"

CaptureRefusal = Literal["screen", "sensitive_app"]


class InteractOutcome(StrEnum):
    """How a desktop_interact call ended."""

    DELIVERED = "delivered"
    """The action reached the element, natively or by the coordinate fallback."""

    UNSUPPORTED = "unsupported"
    """The native route could not perform the action and the coordinate fallback failed too."""

    STALE = "stale"
    """The native action found the element gone or changed; it was reported and not repeated."""

    UNKNOWN = "unknown"
    """The native action may or may not have been delivered; it was reported and not repeated."""

    REFUSED = "refused"
    """A gate or a precondition stopped the call before anything reached the element."""

    ABORTED = "aborted"
    """An exception ended the call before it reached a verdict (a stop, a takeover timeout)."""


@dataclass
class InteractTrace:
    """The path of one desktop_interact call: entering starts the clock, leaving writes the one log line.

    A call that returns without a verdict was refused by a gate, and a call that raises before one was aborted.
    """

    verb: str
    outcome: InteractOutcome = InteractOutcome.ABORTED
    fallback: bool = False
    """The coordinate click was attempted because the native route does not support the action."""
    revalidated: bool = False
    """An approval delay made the call read the application again before acting."""
    _started: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.verb not in _VERBS:
            self.verb = _OTHER_VERB

    def __enter__(self) -> Self:
        self._started = time.monotonic()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if exc_type is None and self.outcome is InteractOutcome.ABORTED:
            self.outcome = InteractOutcome.REFUSED
        logger.info(
            "[DESKTOP] interact verb=%s outcome=%s fallback=%s revalidated=%s duration_ms=%d",
            self.verb,
            self.outcome,
            self.fallback,
            self.revalidated,
            (time.monotonic() - self._started) * 1000,
        )


def log_capture_refused(reason: CaptureRefusal) -> None:
    """Count one screenshot the vision capture entry refused: the screen is unusable, or a sensitive app is in front."""
    logger.info("[DESKTOP] vision_capture outcome=refused reason=%s", reason)
