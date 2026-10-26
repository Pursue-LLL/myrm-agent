"""Browser tools behind the person's control of the browser.

[INPUT]
- utils.runtime.user_control::apply_user_control_gate, ToolRole (POS: process-wide hold on the surface + the tool fence)
- session::BrowserSession (POS: carries the control it consults and the hand-over the model last observed)
- exceptions::UserTakeoverTimeoutError (POS: the browser's error for a wait that outlasted its budget)

[OUTPUT]
- apply_browser_user_control_gate: fence the browser tools in place
- REOBSERVE_NOTICE: the result an action gets when the page may have changed under a person's hands

[POS]
Classifies the eight browser tools for the user-control gate. While a person drives the browser every tool
waits except `browser_ask_human_tool`: the model calls it to hand the browser to the person, and a resumed
run calls it again. Looking tools (snapshot, inspect, extract) re-establish what the model knows; acting
tools (interact, execute_script) refuse to run until the model has looked again. Navigate and manage only
wait. Applied before the cancel boundary so that stopping a run also stops a tool that is waiting.
Names are classified by tool name, so a test pins them to the tools the factories actually build.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.user_control import ToolRole, apply_user_control_gate

from ..exceptions import UserTakeoverTimeoutError

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from ..session import BrowserSession

REOBSERVE_NOTICE = (
    "Not run: a person used the browser since you last looked at the page, so it may have changed. "
    "Take a fresh snapshot, then retry."
)

_ROLES = {
    "browser_snapshot_tool": ToolRole.OBSERVE,
    "browser_inspect_tool": ToolRole.OBSERVE,
    "browser_extract_tool": ToolRole.OBSERVE,
    "browser_interact_tool": ToolRole.ACT,
    "browser_execute_script_tool": ToolRole.ACT,
}
_EXEMPT = frozenset({"browser_ask_human_tool"})


def apply_browser_user_control_gate(tools: list[BaseTool], session: BrowserSession) -> list[BaseTool]:
    """Make every browser tool wait for the person while they drive the browser.

    Accepts the restricted set too, which has no `browser_execute_script_tool`.
    """
    present = {tool.name for tool in tools}
    return apply_user_control_gate(
        tools,
        session,
        roles={name: role for name, role in _ROLES.items() if name in present},
        exempt=_EXEMPT & present,
        reobserve_notice=REOBSERVE_NOTICE,
        timeout_error=lambda timeout_seconds: UserTakeoverTimeoutError(timeout_seconds=timeout_seconds),
    )
