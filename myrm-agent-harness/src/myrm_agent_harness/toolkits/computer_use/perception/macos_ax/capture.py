"""macOS AX tree capture: run the snapshot script and parse its output into @dref elements.

[INPUT]
- scripts::_AX_SNAPSHOT_SCRIPT, _build_ax_snapshot_script, _MAX_ELEMENTS, _SNAPSHOT_ROLE_FILTER (POS: the osascript text and its caps)
- backends.macos.permissions::_MACOS_DEEPLINKS (POS: System Settings deep links)
- backends.macos.background::resolve_app_pid, _set_enhanced_ui (POS: target process id; AXEnhancedUserInterface switch)
- dref.errors::AXPermissionRequiredError, AXTreeEmptyError (POS: AX error types)
- dref.types::ElementRef, SnapshotMeta, SnapshotScope, BBox, INTERACTIVE_AX_ROLES (POS: @dref types)

[OUTPUT]
- capture_ax_snapshot: AX tree capture with targeted app support, auto-unminimize and foreground fallback
- MacAxSnapshot: parsed capture (meta + refs)

[POS]
Capture half of the macOS AX backend. Supports targeted capture by app name (auto-restores minimized windows,
bypasses frontmost) and falls back to the foreground app when the target is not found.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from myrm_agent_harness.toolkits.computer_use.backends.macos.permissions import _MACOS_DEEPLINKS
from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError, AXTreeEmptyError
from myrm_agent_harness.toolkits.computer_use.dref.types import (
    INTERACTIVE_AX_ROLES,
    BBox,
    ElementRef,
    SnapshotMeta,
    SnapshotScope,
)

from .scripts import _AX_SNAPSHOT_SCRIPT, _MAX_ELEMENTS, _SNAPSHOT_ROLE_FILTER, _build_ax_snapshot_script

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MacAxSnapshot:
    meta: SnapshotMeta
    refs: dict[str, ElementRef]


def _resolve_target_app(scope: SnapshotScope, app_name: str | None) -> str | None:
    """Extract target app name from scope. Returns None for foreground mode."""
    if scope == "target" and app_name:
        return app_name
    return None


def _run_ax_snapshot(script: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise AXTreeEmptyError("macOS AX snapshot timed out") from exc


def _parse_ax_output(
    result: subprocess.CompletedProcess[str],
    effective_scope: SnapshotScope,
) -> MacAxSnapshot:
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "不允许辅助访问" in stderr or "not allowed assistive" in stderr.lower():
            raise AXPermissionRequiredError("macOS", _MACOS_DEEPLINKS["accessibility"])
        raise AXTreeEmptyError(stderr or "AppleScript AX snapshot failed")

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise AXTreeEmptyError("no AX output")

    # The AppleScript snapshot script surfaces an AX permission denial as a
    # dedicated marker line (the `entire contents` call is guarded by try/on
    # error inside osascript, so it would otherwise be misreported as an empty
    # tree instead of a missing permission).
    if any(line.startswith("AX_PERMISSION_ERROR|||") for line in lines):
        raise AXPermissionRequiredError("macOS", _MACOS_DEEPLINKS["accessibility"])

    meta_line = lines[0].split("|||")
    # Format: appName|||META|||winTitle|||bundleId|||appPid
    app_name = meta_line[0] if meta_line else ""
    window_name = meta_line[2] if len(meta_line) > 2 else ""
    app_id = meta_line[3] if len(meta_line) > 3 else ""
    pid_str = meta_line[4] if len(meta_line) > 4 else ""
    pid = int(pid_str) if pid_str.isdigit() else 0

    refs: dict[str, ElementRef] = {}
    ref_index = 0
    truncated = len(lines) - 1 >= _MAX_ELEMENTS

    def _restore_text(raw: str) -> str:
        return raw.replace("\x01", "\n")

    for line in lines[1:]:
        parts = line.split("|||")
        if len(parts) < 8:
            continue
        backend_index, role, name, value, x_s, y_s, w_s, h_s = parts[:8]
        if role not in INTERACTIVE_AX_ROLES and role not in set(_SNAPSHOT_ROLE_FILTER):
            continue
        try:
            bbox = BBox(int(float(x_s)), int(float(y_s)), int(float(w_s)), int(float(h_s)))
        except ValueError:
            continue
        if bbox.width <= 0 or bbox.height <= 0:
            continue
        ref_id = f"d{ref_index}"
        actions = ("click", "fill") if role in {"AXTextField", "AXTextArea"} else ("click",)
        refs[ref_id] = ElementRef(
            ref_id=ref_id,
            role=role,
            name=_restore_text(name) or _restore_text(value),
            bbox=bbox,
            backend_key=backend_index,
            actions=actions,
            value=_restore_text(value),
        )
        ref_index += 1

    if not refs:
        raise AXTreeEmptyError(app_name or "frontmost app")

    meta = SnapshotMeta(
        ref_count=len(refs),
        app_name=app_name,
        window_title=window_name,
        scope=effective_scope,
        app_id=app_id,
        pid=pid,
        truncated=truncated,
    )
    return MacAxSnapshot(meta=meta, refs=refs)


def capture_ax_snapshot(
    scope: SnapshotScope,
    app_name: str | None = None,
    query: str | None = None,
    role: str | None = None,
) -> MacAxSnapshot:
    target_app = _resolve_target_app(scope, app_name)

    if target_app is not None:
        # Electron apps hide nodes without AXEnhancedUserInterface; fail-soft.
        from myrm_agent_harness.toolkits.computer_use.backends.macos.background import (
            _set_enhanced_ui,
            resolve_app_pid,
        )

        pid = resolve_app_pid(target_app)
        if pid:
            _set_enhanced_ui(pid)

    if target_app is not None or query or role:
        script = _build_ax_snapshot_script(target_app=target_app, query=query, role=role)
        try:
            result = _run_ax_snapshot(script)
            return _parse_ax_output(result, effective_scope=scope if target_app else "foreground")
        except AXTreeEmptyError:
            if target_app is not None:
                logger.info(
                    "Targeted AX snapshot for '%s' failed, falling back to foreground",
                    target_app,
                )
                if query or role:
                    fallback_script = _build_ax_snapshot_script(query=query, role=role)
                    result = _run_ax_snapshot(fallback_script)
                    return _parse_ax_output(result, effective_scope="foreground")

    result = _run_ax_snapshot(_AX_SNAPSHOT_SCRIPT)
    return _parse_ax_output(result, effective_scope="foreground")
