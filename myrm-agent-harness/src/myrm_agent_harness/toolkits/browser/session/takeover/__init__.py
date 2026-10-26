"""Human takeover of a browser session: the wait a session call makes while a person drives, and its errors.

[INPUT]
- mixin::BrowserSessionTakeoverMixin (POS: the session-level wait before every call that acts on the page)
- errors::UserTakeoverTimeoutError, UserTakeoverDuringScriptError (POS: the two refusals of that wait)

[OUTPUT]
- BrowserSessionTakeoverMixin: `_ensure_not_user_takeover` for the BrowserSession aggregate root
- UserTakeoverTimeoutError, UserTakeoverDuringScriptError: what the wait raises and the tool layer reports

[POS]
Session-level half of the human-takeover fence; the tool gate (tools/user_control_gate.py) is the other half.
Its errors live beside the wait that raises them, so the tool layer imports them from here.
"""

from .errors import UserTakeoverDuringScriptError, UserTakeoverTimeoutError
from .mixin import BrowserSessionTakeoverMixin

__all__ = [
    "BrowserSessionTakeoverMixin",
    "UserTakeoverDuringScriptError",
    "UserTakeoverTimeoutError",
]
