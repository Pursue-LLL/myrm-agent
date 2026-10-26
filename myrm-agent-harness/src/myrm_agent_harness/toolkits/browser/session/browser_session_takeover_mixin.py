"""BrowserSession wait for a person who drives the browser.

[INPUT]
- session_host::SessionHost (POS: typed contract of the attributes the aggregate root provides, here the process-wide control hold)
- utils.runtime.user_control::DEFAULT_WAIT_TIMEOUT_S, UserControlTimeoutError, plan_is_stale (POS: wait budget, timeout error and the script pin)
- takeover_errors::UserTakeoverTimeoutError, UserTakeoverDuringScriptError (POS: errors of the human-takeover wait)

[OUTPUT]
- BrowserSessionTakeoverMixin: `_ensure_not_user_takeover`, the wait every session call that acts on the page makes first

[POS]
Session-level half of the human-takeover fence; the tool gate (tools/user_control_gate.py) is the other half.
The gate vets a tool call once, before it starts, so this wait covers session calls made outside a tool
and the later steps of a script. The session stays locked on timeout rather than act behind the person's back.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.runtime.user_control import DEFAULT_WAIT_TIMEOUT_S, UserControlTimeoutError, plan_is_stale

from ..takeover_errors import UserTakeoverDuringScriptError, UserTakeoverTimeoutError
from .session_host import SessionHost

logger = logging.getLogger(__name__)


class BrowserSessionTakeoverMixin(SessionHost):
    async def _ensure_not_user_takeover(self, timeout: float = DEFAULT_WAIT_TIMEOUT_S) -> None:
        """Wait while a person drives the browser; refuse once they keep it past `timeout`.

        The tool gate vets a tool call once, before it starts, so this covers session calls made outside a
        tool and the later steps of a script. The session stays locked on timeout rather than act behind
        the person's back.

        Raises:
            UserTakeoverTimeoutError: the person still drives after `timeout` seconds.
            UserTakeoverDuringScriptError: a running script's plan predates the person's last turn at the page.
        """
        try:
            await self.user_control.wait_released(timeout)
        except UserControlTimeoutError as exc:
            logger.error("User takeover wait timed out (%.1fs); session stays locked", timeout)
            raise UserTakeoverTimeoutError(timeout_seconds=exc.timeout_seconds) from exc
        if plan_is_stale(self.user_control):
            raise UserTakeoverDuringScriptError
