"""Errors raised while a person drives the browser the agent works in.

[INPUT]
- exceptions::BrowserError (POS: root of the browser toolkit exception hierarchy)

[OUTPUT]
- UserTakeoverTimeoutError: a person kept control of the browser longer than the wait budget
- UserTakeoverDuringScriptError: a script's next step comes after a person used the page it was planned against

[POS]
The two ways the user-control fence refuses a browser call that cannot simply wait: the person never gave
control back, or the plan a running script follows predates what the person did to the page. Both read as
tool errors to the model, so their text says what did not happen and what to do next.
"""

from __future__ import annotations

from .exceptions import BrowserError


class UserTakeoverTimeoutError(BrowserError):
    """Raised when an operation times out waiting for human user takeover to complete."""

    def __init__(
        self,
        message: str = "User takeover wait timed out; the browser stays locked until the person hands control back",
        *,
        timeout_seconds: float = 600.0,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            message,
            context={"timeout_seconds": timeout_seconds, **(context or {})},
            error_code="USER_TAKEOVER_TIMEOUT",
            recovery_suggestions=[
                "Wait for the user to complete their takeover in the browser or VNC window",
                "Ask the user if they wish to resume the session or abort the task",
            ],
        )


class UserTakeoverDuringScriptError(BrowserError):
    """Raised inside a running script when a person used the browser after the script was planned.

    The script was written from what the model saw before the person acted, so its remaining steps
    must not run against whatever they left on the page.
    """

    def __init__(
        self,
        message: str = (
            "Script stopped: a person used the browser while it was running, so the page may have changed "
            "under the remaining steps. The steps before this one already ran. "
            "Take a fresh snapshot and check what the page shows now before doing anything else."
        ),
    ) -> None:
        super().__init__(
            message,
            error_code="USER_TAKEOVER_DURING_SCRIPT",
            recovery_suggestions=["Take a fresh snapshot, then plan the remaining steps from what the page shows now"],
        )
