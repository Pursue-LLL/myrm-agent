"""macOS AX element invocation via AppleScript.

[INPUT]
- scripts::_AX_INVOKE_SCRIPT, _build_ax_invoke_script (POS: the osascript text of one element action)
- perception.ax_result::{AxFailure, AxInvokeResult} (POS: typed outcome of a native action)

[OUTPUT]
- invoke_ax_element: AX element invocation with targeted app support; a failure says whether anything may have been delivered

[POS]
Invoke half of the macOS AX backend; the element is addressed by the backend key a capture produced.
"""

from __future__ import annotations

import re
import subprocess

from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult

from .scripts import _AX_INVOKE_SCRIPT, _build_ax_invoke_script

# AppleScript error numbers (the localized message text varies, the number does not): the object or the list index
# the script asked for does not exist, so the element or its window is gone.
_ELEMENT_GONE = frozenset({"-1728", "-1719"})
# osascript may not drive the UI (assistive access, or sending Apple events to System Events): nothing ran.
_NOT_PERMITTED = frozenset({"-25211", "-1743"})
_ERROR_NUMBER = re.compile(r"\((-?\d+)\)\s*$")


def _permission_denied(stderr: str) -> bool:
    return "不允许辅助访问" in stderr or "not allowed assistive" in stderr.lower()


def _classify_script_error(stderr: str, returncode: int, ax_action: str) -> AxFailure:
    """What a failed script run proves about delivery.

    A value that could not be set was not set, so a failed fill leaves the element as it was. A failed click may
    already have fallen through to the script's second attempt, so it proves nothing.
    """
    number = match.group(1) if (match := _ERROR_NUMBER.search(stderr)) else ""
    if number in _NOT_PERMITTED:
        return AxFailure.UNSUPPORTED
    if number in _ELEMENT_GONE:
        return AxFailure.STALE
    if returncode > 0 and ax_action == "fill":
        return AxFailure.UNSUPPORTED
    return AxFailure.UNKNOWN


def invoke_ax_element(
    backend_key: str,
    action: str,
    text: str = "",
    app_name: str | None = None,
) -> AxInvokeResult:
    normalized_action = action.lower()
    if normalized_action in {"dblclick", "double_click"}:
        normalized_action = "click"
    # `type` is not performed here: it is refused as unsupported, so the caller's coordinate fallback types the keys.
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
        return AxInvokeResult.failed(AxFailure.UNSUPPORTED, f"Unsupported AX action: {action}")

    ax_action = "fill" if normalized_action in {"fill", "set_value"} else "click"
    invoke_script = _build_ax_invoke_script(target_app=app_name) if app_name else _AX_INVOKE_SCRIPT
    try:
        result = subprocess.run(
            ["osascript", "-e", invoke_script, ax_action, backend_key, text],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return AxInvokeResult.failed(AxFailure.UNKNOWN, "AX invoke timed out")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if _permission_denied(stderr):
            return AxInvokeResult.failed(AxFailure.UNSUPPORTED, "Accessibility permission required on macOS")
        failure = _classify_script_error(stderr, result.returncode, ax_action)
        return AxInvokeResult.failed(failure, stderr or "AX invoke failed")

    if result.stdout.strip() != "OK":
        return AxInvokeResult.failed(AxFailure.UNKNOWN, result.stdout.strip() or "AX invoke failed")
    return AxInvokeResult.delivered(f"AX {ax_action} succeeded")
