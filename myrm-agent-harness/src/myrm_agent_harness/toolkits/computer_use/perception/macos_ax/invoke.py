"""macOS AX element invocation via AppleScript.

[INPUT]
- scripts::_AX_INVOKE_SCRIPT, _build_ax_invoke_script (POS: the osascript text of one element action)
- types::ActionResult (POS: action result container)

[OUTPUT]
- invoke_ax_element: AX element invocation with targeted app support

[POS]
Invoke half of the macOS AX backend; the element is addressed by the backend key a capture produced.
"""

from __future__ import annotations

import subprocess

from myrm_agent_harness.toolkits.computer_use.types import ActionResult

from .scripts import _AX_INVOKE_SCRIPT, _build_ax_invoke_script


def invoke_ax_element(
    backend_key: str,
    action: str,
    text: str = "",
    app_name: str | None = None,
) -> ActionResult:
    normalized_action = action.lower()
    if normalized_action in {"dblclick", "double_click"}:
        normalized_action = "click"
    if normalized_action not in {
        "click",
        "fill",
        "set_value",
        "press",
        "focus",
        "hover",
        "toggle",
        "expand",
        "collapse",
        "invoke",
        "check",
        "uncheck",
    }:
        return ActionResult(success=False, error=f"Unsupported AX action: {action}")

    ax_action = "fill" if normalized_action in {"fill", "type", "set_value"} else "click"
    invoke_script = _build_ax_invoke_script(target_app=app_name) if app_name else _AX_INVOKE_SCRIPT
    try:
        result = subprocess.run(
            ["osascript", "-e", invoke_script, ax_action, backend_key, text],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return ActionResult(success=False, error="AX invoke timed out")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "不允许辅助访问" in stderr or "not allowed assistive" in stderr.lower():
            return ActionResult(success=False, error="Accessibility permission required on macOS")
        return ActionResult(success=False, error=stderr or "AX invoke failed")

    if result.stdout.strip() != "OK":
        return ActionResult(success=False, error=result.stdout.strip() or "AX invoke failed")
    return ActionResult(success=True, output=f"AX {ax_action} succeeded")
