"""TextEdit fixture helpers for desktop approval Chrome E2E (macOS only)."""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import time

from tests.e2e.desktop_approval.constants import TEXTEDIT_FIXTURE_MARKER, progress


def _pytest_fail(message: str) -> None:
    import pytest

    pytest.fail(message)

_TEXTEDIT_AX_DEGRADED_TTL_SEC = 300.0
_STRICT_FALLBACK_MODE_ENV = "MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE"
_textedit_ax_degraded_until_monotonic = 0.0
_textedit_ax_degraded_detail = ""
_textedit_ax_degraded_scope_key = ""


def _runtime_scope_key() -> str:
    raw = os.getenv("PYTEST_CURRENT_TEST", "").strip()
    if not raw:
        return "global"
    return raw.split(" (", 1)[0].strip() or "global"


def _strict_fallback_mode_enabled() -> bool:
    raw = os.getenv(_STRICT_FALLBACK_MODE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _textedit_ax_degraded_snapshot() -> tuple[bool, str, int]:
    if (
        _textedit_ax_degraded_scope_key
        and _textedit_ax_degraded_scope_key != _runtime_scope_key()
    ):
        _clear_textedit_ax_degraded()
        return False, "", 0
    remaining = int(
        max(0.0, _textedit_ax_degraded_until_monotonic - time.monotonic())
    )
    return remaining > 0, _textedit_ax_degraded_detail, remaining


def _mark_textedit_ax_degraded(detail: str) -> None:
    global _textedit_ax_degraded_until_monotonic
    global _textedit_ax_degraded_detail, _textedit_ax_degraded_scope_key
    _textedit_ax_degraded_until_monotonic = (
        time.monotonic() + _TEXTEDIT_AX_DEGRADED_TTL_SEC
    )
    _textedit_ax_degraded_detail = detail.strip() or "unknown"
    _textedit_ax_degraded_scope_key = _runtime_scope_key()


def _clear_textedit_ax_degraded() -> None:
    global _textedit_ax_degraded_until_monotonic
    global _textedit_ax_degraded_detail, _textedit_ax_degraded_scope_key
    _textedit_ax_degraded_until_monotonic = 0.0
    _textedit_ax_degraded_detail = ""
    _textedit_ax_degraded_scope_key = ""


def _reset_textedit_fixture_runtime_state_for_tests() -> None:
    _clear_textedit_ax_degraded()


def _run_command_no_raise(
    args: list[str],
    *,
    timeout: int,
    label: str,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        progress(f"{label} timed out after {timeout}s")
        return None


def _force_kill_textedit_process(*, include_sigkill: bool) -> None:
    _run_command_no_raise(
        ["pkill", "-x", "TextEdit"],
        timeout=5,
        label="textedit pkill",
    )
    if include_sigkill:
        _run_command_no_raise(
            ["pkill", "-9", "-x", "TextEdit"],
            timeout=5,
            label="textedit pkill -9",
        )


def textedit_fixture_ready() -> bool:
    if platform.system() != "Darwin":
        return False
    proc = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "TextEdit"',
            "-e",
            "if not running then return false",
            "-e",
            "if (count of documents) is 0 then return false",
            "-e",
            f'return text of document 1 contains "{TEXTEDIT_FIXTURE_MARKER}"',
            "-e",
            "end tell",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def _probe_textedit_ax_ready() -> tuple[bool, str]:
    """Return whether TextEdit AX snapshot currently has usable refs."""
    if platform.system() != "Darwin":
        return False, "unsupported-platform"
    from myrm_agent_harness.toolkits.computer_use.backends.macos import MacOSBackend
    from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef
    from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import (
        capture_snapshot,
    )

    backend = MacOSBackend()
    probes: tuple[tuple[str, str | None], ...] = (
        ("window_title", "TextEdit"),
        ("foreground", None),
    )
    diagnostics: list[str] = []
    for scope, window_title in probes:
        try:
            meta, refs = capture_snapshot(backend, scope, window_title)
        except Exception as exc:  # noqa: BLE001 - diagnostics for E2E recovery
            diagnostics.append(f"{scope}: {type(exc).__name__}: {exc}")
            continue
        ref_count = sum(1 for value in refs.values() if isinstance(value, ElementRef))
        if ref_count <= 0:
            diagnostics.append(
                f"{scope}: empty refs app={meta.app_name!r} window={meta.window_title!r}"
            )
            continue
        if scope == "window_title" and str(meta.app_name or "").strip() != "TextEdit":
            diagnostics.append(
                f"{scope}: unexpected app {meta.app_name!r} with refs={ref_count}"
            )
            continue
        return (
            True,
            f"{scope}: app={meta.app_name!r} window={meta.window_title!r} refs={ref_count}",
        )
    detail = "; ".join(diagnostics[:4]) if diagnostics else "no-probe-result"
    return False, detail


def prepare_textedit_fixture() -> None:
    """Open TextEdit in the background and seed scrollable fixture text without stealing focus."""
    if platform.system() != "Darwin":
        return
    _run_command_no_raise(
        ["open", "-gj", "-a", "TextEdit"],
        timeout=10,
        label="textedit open",
    )
    seed_proc = _run_command_no_raise(
        [
            "osascript",
            "-e",
            'tell application "TextEdit"',
            "-e",
            "if not running then launch",
            "-e",
            "if (count of documents) is 0 then make new document",
            "-e",
            'set text of document 1 to "E2E desktop control scroll target line 1" & return & "E2E desktop control scroll target line 2" & return & "E2E desktop control scroll target line 3" & return & "E2E desktop control scroll target line 4" & return & "E2E desktop control scroll target line 5"',
            "-e",
            "end tell",
        ],
        timeout=20,
        label="textedit prepare",
    )
    if seed_proc is None:
        progress("textedit prepare timed out; force-kill fallback")
        _force_kill_textedit_process(include_sigkill=True)
        return
    if seed_proc.returncode != 0:
        progress(
            "textedit prepare returned non-zero; force-kill fallback "
            f"code={seed_proc.returncode}"
        )
        _force_kill_textedit_process(include_sigkill=True)
        return


def restart_textedit_fixture_process() -> None:
    """Hard-restart TextEdit when AX snapshots remain empty."""
    if platform.system() != "Darwin":
        return
    quit_proc = _run_command_no_raise(
        ["osascript", "-e", 'tell application "TextEdit" to quit'],
        timeout=10,
        label="textedit quit",
    )
    if quit_proc is None:
        progress("textedit quit timed out after 10s; force-kill fallback")
        _force_kill_textedit_process(include_sigkill=True)
    elif quit_proc.returncode != 0:
        progress(
            "textedit quit returned non-zero; force-kill fallback "
            f"code={quit_proc.returncode}"
        )
        _force_kill_textedit_process(include_sigkill=False)
    time.sleep(0.6)
    prepare_textedit_fixture()
    time.sleep(1.5)


def hide_textedit_fixture() -> None:
    """Keep the fixture reachable via AX without stealing user focus."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to tell process "TextEdit" to repeat with w in windows',
            "-e",
            "set miniaturized of w to true",
            "-e",
            "end repeat",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _textedit_osascript_timeout_sec(*, activate: bool = False) -> float:
    signoff = os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    if activate:
        return 25.0 if signoff else 15.0
    return 20.0 if signoff else 10.0


def activate_textedit_foreground() -> None:
    """Bring TextEdit to the foreground so macOS AX snapshot returns @drefs."""
    if platform.system() != "Darwin":
        return
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "TextEdit" to activate',
                "-e",
                'tell application "System Events" to tell process "TextEdit" to repeat with w in windows',
                "-e",
                "set miniaturized of w to false",
                "-e",
                "end repeat",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=_textedit_osascript_timeout_sec(activate=True),
        )
    except subprocess.TimeoutExpired:
        progress(
            "textedit activate osascript timeout — continue preflight retries"
        )


def activate_chrome_foreground() -> None:
    """Bring Chrome E2E browser to the foreground for CDP polling and approval UI."""
    if platform.system() != "Darwin":
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "Google Chrome" to activate'],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def textedit_is_frontmost() -> bool:
    """True when TextEdit is the frontmost app (AX snapshot targets foreground window)."""
    if platform.system() != "Darwin":
        return False
    try:
        proc = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to return name of first application process whose frontmost is true',
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=_textedit_osascript_timeout_sec(),
        )
    except subprocess.TimeoutExpired:
        progress(
            "textedit is_frontmost osascript timeout — treating as not frontmost"
        )
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "TextEdit"


def preflight_textedit_foreground(
    *,
    attempts: int = 5,
    fail_hard: bool = True,
) -> bool:
    """Ensure TextEdit is un-minimized and frontmost before agent desktop tools run."""
    if platform.system() != "Darwin":
        return True
    for attempt in range(1, attempts + 1):
        activate_textedit_foreground()
        settle_sec = 0.8 if os.environ.get("E2E_SIGNOFF", "").strip() == "1" else 0.35
        time.sleep(settle_sec)
        is_frontmost = textedit_is_frontmost()
        if is_frontmost:
            progress(f"textedit foreground preflight ok (attempt {attempt}/{attempts})")
            return True
        progress(
            f"textedit foreground preflight retry {attempt}/{attempts} "
            f"(frontmost={is_frontmost})"
        )
    if not fail_hard:
        return False
    _pytest_fail(
        "TextEdit not frontmost after preflight — desktop_snapshot will miss @drefs "
        "and the model may fall back to desktop_vision_tool"
    )
    return False


def ensure_textedit_ax_ready(*, attempts: int = 3) -> bool:
    """Ensure TextEdit AX tree is usable, with process rebuild on failure."""
    if platform.system() != "Darwin":
        return True
    last_detail = "unknown"
    for attempt in range(1, attempts + 1):
        foreground_ok = preflight_textedit_foreground(attempts=3, fail_hard=False)
        ax_ready, detail = _probe_textedit_ax_ready()
        last_detail = detail
        if foreground_ok and ax_ready:
            _clear_textedit_ax_degraded()
            progress(f"textedit AX probe ready ({detail})")
            return True
        progress(
            f"textedit AX probe not ready ({attempt}/{attempts}) "
            f"foreground_ok={foreground_ok} detail={detail}"
        )
        if attempt < attempts:
            restart_textedit_fixture_process()
            time.sleep(1.0)
    progress(f"textedit AX probe exhausted: {last_detail}")
    return False


async def ensure_textedit_fixture_ready(*, attempts: int = 5) -> None:
    if platform.system() != "Darwin":
        return
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        attempts = max(attempts, 8)
    last_detail = "unknown"
    for attempt in range(1, attempts + 1):
        await asyncio.to_thread(prepare_textedit_fixture)
        marker_ready = await asyncio.to_thread(textedit_fixture_ready)
        if marker_ready:
            degraded, degraded_detail, degraded_remaining = (
                _textedit_ax_degraded_snapshot()
            )
            if degraded:
                if _strict_fallback_mode_enabled():
                    _pytest_fail(
                        "TextEdit AX degraded cooldown active while strict fallback mode is enabled "
                        f"(remaining={degraded_remaining}s detail={degraded_detail})"
                    )
                progress(
                    "textedit AX degraded mode active; skip rebuild and continue "
                    "with vision fallback "
                    f"(remaining={degraded_remaining}s detail={degraded_detail})"
                )
                return
            ax_ready = await asyncio.to_thread(ensure_textedit_ax_ready, attempts=4)
            if ax_ready:
                progress("textedit fixture ready (foreground + AX refs for @drefs)")
                return
            if _strict_fallback_mode_enabled():
                _pytest_fail(
                    "TextEdit AX refs unavailable while strict fallback mode is enabled "
                    "(strict mode requires AX-ready fixture before desktop flow)"
                )
            last_detail = "ax-empty-after-rebuild"
            _mark_textedit_ax_degraded(last_detail)
            # AX can be transiently unavailable on some hosts. Continue with
            # vision/snapshot fallback path instead of hard-failing bootstrap.
            progress(
                "textedit marker ready but AX refs unavailable; "
                "continue with vision fallback"
            )
            return
        else:
            last_detail = "marker-missing"
        progress(
            f"textedit fixture not ready yet ({attempt}/{attempts}) "
            f"reason={last_detail}"
        )
        if attempt < attempts:
            if (
                os.environ.get("E2E_SIGNOFF", "").strip() == "1"
                and attempt <= 4
            ):
                await asyncio.to_thread(activate_textedit_foreground)
                await asyncio.sleep(1.5)
            else:
                await asyncio.to_thread(restart_textedit_fixture_process)
                await asyncio.sleep(0.6)
    _pytest_fail(
        "TextEdit fixture not AX-ready after retries "
        f"(last_reason={last_detail}) — verify Accessibility permission and retry"
    )
