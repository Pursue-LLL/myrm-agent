"""browser_execute_script tool for Code-as-Action batch execution.

[INPUT]
- common::mark_untrusted (POS: unified browser output security boundary; credential redaction + untrusted-content wrapping)
- session.browser_session::BrowserSession (POS: browser session)
- script_runtime::ScriptRejectedError, wrap_script, run_script (POS: runs a script in an isolated Monty worker whose only reach into the browser is `interact` and `evaluate`)
- utils.runtime.user_control::planned_against (POS: pins the script's steps to the hand-over the model last observed)

[OUTPUT]
- create_execute_script_tool: Create browser_execute_script tool bound to session.

[POS]
Allows the agent to write and run a Python script that performs batch browser actions, bypassing the
single-step bottleneck. The script never runs in this process (`script_runtime` runs it in an isolated worker);
this module builds the tool the model sees, whose description is the whole script contract, and sets
`session._hitl_caller_tool` for semantic HITL audit attribution while the script runs. The tool gate vets the
call once, before it starts, so the script runs pinned to the hand-over the model last observed
(`planned_against`): when a person used the page meanwhile, its next session step stops the script and the
output says the earlier steps already ran. `verify_goal` checks the visual outcome afterwards.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from myrm_agent_harness.utils.runtime.user_control import planned_against

from .common import mark_untrusted
from .script_runtime import ScriptRejectedError, run_script, wrap_script

if TYPE_CHECKING:
    from ..session import BrowserSession

logger = logging.getLogger(__name__)


# Wall-clock limit of one script run; the tool description states the same number to the model.
_SCRIPT_TIMEOUT_S = 60.0

# The script contract the model sees. Besides it the model gets only the two parameter descriptions of
# ``ExecuteScriptInput``: with ``args_schema`` LangChain takes the description from this argument (or the function
# docstring), never from the schema class docstring.
_TOOL_DESCRIPTION = (
    "Run an async Python script to perform batch browser actions in one call.\n\n"
    "The script is the body of `async def (session, refs)`: "
    "`await session.interact(action, ref, text)` takes the same actions as browser_interact_tool, "
    "and `refs` maps ref ID -> {role, name}. "
    "`print()` output is returned as the result. "
    f"Imports and `open` are unavailable; the script times out after {_SCRIPT_TIMEOUT_S:.0f} s."
)


def create_execute_script_tool(session: BrowserSession) -> BaseTool:
    """Create browser_execute_script tool bound to session."""

    class ExecuteScriptInput(BaseModel):
        script: str = Field(
            description="The async Python script to execute. Do not include `async def` wrapper, just the code body."
        )
        verify_goal: str | None = Field(
            default=None,
            description="Optional natural language description of expected visual outcome (e.g. 'Success message is shown'). Automatically verifies visual result and returns feedback.",
        )

    @tool("browser_execute_script_tool", args_schema=ExecuteScriptInput, description=_TOOL_DESCRIPTION)
    async def browser_execute_script(script: str, verify_goal: str | None = None) -> str:
        try:
            code = wrap_script(script)
        except ScriptRejectedError as exc:
            return str(exc)

        refs: dict[str, dict[str, str | int | None]] = {
            ref_id: {"role": info.role, "name": info.name, "nth": info.nth}
            for ref_id, info in session.get_all_refs().items()
        }

        baseline_screenshot = None
        if verify_goal:
            try:
                page = session._tab_controller.get_active_page()
                from myrm_agent_harness.toolkits.browser.utils.selectors import PASSWORD_FIELD_SELECTOR

                password_locator = page.locator(PASSWORD_FIELD_SELECTOR)
                baseline_screenshot = await page.screenshot(type="png", full_page=False, mask=[password_locator])
            except Exception as e:
                logger.warning("Failed to take baseline screenshot for verification: %s", e)

        session._hitl_caller_tool = "browser_execute_script_tool"
        try:
            await session.notify_progress("Starting browser script execution...")
            # Every step stays pinned to what the model had observed when the script began
            with planned_against(session.observed_generation):
                output = await run_script(
                    session, code, refs, timeout_s=_SCRIPT_TIMEOUT_S, progress=session.notify_progress
                )
        finally:
            session._hitl_caller_tool = None
            await session.notify_progress("Browser script execution completed.")

        if verify_goal and baseline_screenshot:
            try:
                page = session._tab_controller.get_active_page()
                await session.notify_progress(f"Verifying script goal: '{verify_goal}'...")
                _success, verify_msg = await session._vision_verifier.verify_action(
                    page=page,
                    baseline_screenshot=baseline_screenshot,
                    verify_goal=verify_goal,
                )
                output += f"\n\n{verify_msg}"
            except Exception as e:
                output += f"\n\nVerification failed: {e}"

        return mark_untrusted(output.strip() or "Script executed successfully with no output.")

    return browser_execute_script
