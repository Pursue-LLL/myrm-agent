"""Typed outcome of one native AX element action.

[INPUT]
- types::ActionResult (POS: action result container)

[OUTPUT]
- AxFailure: what a failed native action proves (UNSUPPORTED, STALE or UNKNOWN)
- AxInvokeResult: ActionResult that carries its AxFailure

[POS]
Result contract shared by the macOS, Windows and Linux invokers and `desktop_interact`, which falls back to a
coordinate click only after UNSUPPORTED, the one failure that proves nothing reached the element it meant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from myrm_agent_harness.toolkits.computer_use.types import ActionResult


class AxFailure(StrEnum):
    UNSUPPORTED = "unsupported"
    """The native route cannot do this on the element (no permission, no such action, no editable text): nothing
    was delivered and the element's coordinates still point at it."""

    STALE = "stale"
    """The element or its window is gone or has changed: its old coordinates may belong to something else now."""

    UNKNOWN = "unknown"
    """The action may or may not have been delivered, so repeating it could deliver it twice."""


@dataclass
class AxInvokeResult(ActionResult):
    """Outcome of a native action; `failure` is None exactly when the action was delivered."""

    failure: AxFailure | None = None

    @classmethod
    def delivered(cls, output: str) -> AxInvokeResult:
        return cls(success=True, output=output)

    @classmethod
    def failed(cls, failure: AxFailure, error: str) -> AxInvokeResult:
        return cls(success=False, error=error, failure=failure)
