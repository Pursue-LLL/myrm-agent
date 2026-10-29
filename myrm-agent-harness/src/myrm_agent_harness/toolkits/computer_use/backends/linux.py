"""Linux backend — scrot/gnome-screenshot + xdotool.

Covers both native Linux desktops and SaaS sandbox environments (which run Linux).

[INPUT]
- types::ScreenInfo, ScreenContext, ActionResult, WindowTextResult (POS: shared type definitions)
- linux_probes::detect_linux_resolution, read_screen_context, linux_permission_status (POS: read-only screen and environment probes)
- linux_text_io::X11TextInput (POS: text bridge of the Linux backend)

[OUTPUT]
- LinuxBackend: ComputerBackend implementation for Linux

[POS]
Linux-specific screen I/O. Loaded for detect_platform().os_type == "linux".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shlex
import shutil
import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.computer_use.backends.linux_probes import (
    detect_linux_resolution,
    linux_permission_status,
    read_screen_context,
)
from myrm_agent_harness.toolkits.computer_use.backends.linux_text_io import X11TextInput
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    ModifierKey,
    PermissionStatus,
    ScreenContext,
    ScreenInfo,
    ScreenLockState,
    WindowTextResult,
)

logger = logging.getLogger(__name__)

_TIMEOUT_EXIT_CODE = 124
_COMMAND_NOT_FOUND_EXIT_CODE = 127
# xdotool exits 0 when it skips a key name it does not know, so the exit code alone reports a key that never fired.
_UNKNOWN_KEY_MARKER = "No such key name"

CLICK_BUTTONS = {
    "left": "1",
    "right": "3",
    "middle": "2",
}

_MODIFIER_TO_XDOTOOL: dict[ModifierKey, str] = {
    "ctrl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "meta": "super",
}


def _parse_display_num() -> int | None:
    """Extract display number from $DISPLAY env var (e.g. ':1' → 1, ':99.0' → 99)."""
    display = os.getenv("DISPLAY", "")
    if ":" in display:
        try:
            return int(display.split(":")[1].split(".")[0])
        except (ValueError, IndexError):
            pass
    return None


class LinuxBackend:
    """Linux screen I/O via scrot/gnome-screenshot + xdotool."""

    def __init__(self, display_num: int | None = None) -> None:
        self._screen_info: ScreenInfo | None = None
        self._display_num = display_num if display_num is not None else _parse_display_num()
        self._text_input = X11TextInput(self._run_cmd, self._run_input)

    def _subprocess_env(self) -> dict[str, str] | None:
        """Environment that selects this backend's display; None inherits the process environment."""
        if self._display_num is None:
            return None
        return {**os.environ, "DISPLAY": f":{self._display_num}"}

    async def _run_cmd(
        self, cmd: str, stdin: str | None = None, timeout: float | None = None, *, capture: bool = True
    ) -> tuple[str, str, int]:
        """Run a command without a shell; `stdin` is piped, not put on the command line.

        With `timeout`, a command that has not finished by then is killed and reported as exit 124. A cancelled
        call kills the command too, so it cannot keep injecting input after its caller is gone. `capture=False`
        leaves stdout/stderr unpiped for tools that fork a long-lived child (xclip).
        """
        argv = shlex.split(cmd)
        sink = asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if stdin is not None else None,
                stdout=sink,
                stderr=sink,
                env=self._subprocess_env(),
            )
        except FileNotFoundError:
            return "", f"{argv[0]}: command not found", _COMMAND_NOT_FOUND_EXIT_CODE
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin.encode("utf-8") if stdin is not None else None), timeout
            )
        except TimeoutError:
            # A timeout can coincide with the process exiting on its own, and kill() then raises ProcessLookupError.
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            # The command line may carry typed text, so it stays out of the log.
            logger.warning("An X11 helper command timed out after %ss and was killed", timeout)
            return "", f"timed out after {timeout}s", _TIMEOUT_EXIT_CODE
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            raise
        return (
            (stdout or b"").decode(errors="replace"),
            (stderr or b"").decode(errors="replace"),
            proc.returncode or 0,
        )

    async def _run_input(self, cmd: str, stdin: str | None = None, *, capture: bool = True) -> None:
        """Run an input-injection command; a non-zero exit (e.g. xdotool missing) must not look like success."""
        _, stderr, code = await self._run_cmd(cmd, stdin, capture=capture)
        if code != 0 or _UNKNOWN_KEY_MARKER in stderr:
            detail = f": {stderr.strip()}" if stderr.strip() else ""
            raise RuntimeError(f"{cmd.split()[0]} failed (exit {code}){detail}")

    async def resolve_window_target(self, app_name: str, window_index: int = 0) -> tuple[int, int, int, int] | None:
        """Window targeting is unsupported here: no window can be resolved."""
        return None

    async def screenshot(self, app_name: str | None = None, window_index: int = 0) -> bytes:
        if app_name:
            raise RuntimeError("window-targeted capture is not supported on Linux; use scope='foreground'")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            if shutil.which("gnome-screenshot"):
                cmd = f"gnome-screenshot -f {tmp_path} -p"
            elif shutil.which("scrot"):
                cmd = f"scrot -p {tmp_path}"
            else:
                raise RuntimeError("No screenshot tool found (install gnome-screenshot or scrot)")

            _stdout, stderr, returncode = await self._run_cmd(cmd)
            if returncode != 0:
                raise RuntimeError(f"Screenshot failed: {stderr}")
            return tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)

    async def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        modifiers: list[ModifierKey] | None = None,
    ) -> ActionResult:
        xdotool_mods = [_MODIFIER_TO_XDOTOOL[m] for m in modifiers] if modifiers else []
        try:
            btn = CLICK_BUTTONS.get(button, "1")
            await self._run_input(f"xdotool mousemove --sync {x} {y}")

            for mod in xdotool_mods:
                await self._run_input(f"xdotool keydown {mod}")

            if clicks > 1:
                repeat_flag = f"--repeat {clicks} --delay 100"
                await self._run_input(f"xdotool click {repeat_flag} {btn}")
            else:
                await self._run_input(f"xdotool click {btn}")

            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))
        finally:
            for mod in reversed(xdotool_mods):
                await self._run_cmd(f"xdotool keyup {mod}")

    async def type_text(self, text: str, delay_ms: int = 12, chunk_size: int = 50) -> ActionResult:
        """Type text: ASCII as key events, any text with other scripts through the clipboard."""
        try:
            await self._text_input.enter(text, delay_ms, chunk_size)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def key(self, keys: str) -> ActionResult:
        try:
            # The keys come from the model; quoting keeps them arguments instead of shell code.
            await self._run_input(f"xdotool key -- {shlex.join(keys.replace('+', ' ').split())}")
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def mouse_move(self, x: int, y: int) -> ActionResult:
        try:
            await self._run_input(f"xdotool mousemove --sync {x} {y}")
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def scroll(
        self,
        x: int,
        y: int,
        direction: str,
        amount: int = 3,
        modifiers: list[ModifierKey] | None = None,
    ) -> ActionResult:
        xdotool_mods = [_MODIFIER_TO_XDOTOOL[m] for m in modifiers] if modifiers else []
        try:
            await self._run_input(f"xdotool mousemove --sync {x} {y}")

            for mod in xdotool_mods:
                await self._run_input(f"xdotool keydown {mod}")

            scroll_map = {"up": "4", "down": "5", "left": "6", "right": "7"}
            btn = scroll_map.get(direction, "5")
            for _ in range(amount):
                await self._run_input(f"xdotool click {btn}")

            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))
        finally:
            for mod in reversed(xdotool_mods):
                await self._run_cmd(f"xdotool keyup {mod}")

    async def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        modifiers: list[ModifierKey] | None = None,
    ) -> ActionResult:
        xdotool_mods = [_MODIFIER_TO_XDOTOOL[m] for m in modifiers] if modifiers else []
        try:
            for mod in xdotool_mods:
                await self._run_input(f"xdotool keydown {mod}")

            await self._run_input(
                f"xdotool mousemove --sync {start_x} {start_y} mousedown 1 mousemove --sync {end_x} {end_y} mouseup 1"
            )

            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))
        finally:
            for mod in reversed(xdotool_mods):
                await self._run_cmd(f"xdotool keyup {mod}")

    async def wait(self, seconds: float) -> ActionResult:
        await asyncio.sleep(seconds)
        return ActionResult(success=True)

    def screen_info(self) -> ScreenInfo:
        if self._screen_info is not None:
            return self._screen_info

        width = int(os.getenv("WIDTH", "0"))
        height = int(os.getenv("HEIGHT", "0"))

        if not width or not height:
            width, height = detect_linux_resolution(self._subprocess_env())

        self._screen_info = ScreenInfo(width=width, height=height, dpi_scale=1.0)
        return self._screen_info

    def screen_context(self) -> ScreenContext:
        return read_screen_context(self._subprocess_env())

    async def window_text(self) -> WindowTextResult:
        """Extract text from frontmost window via xdotool + xprop.

        Linux lacks a unified accessibility text API like macOS AX.
        Falls back to window name + WM class as minimal context.
        """
        try:
            result = await self._run_cmd("xdotool getactivewindow getwindowname")
            win_title = result[0].strip() if result[2] == 0 else ""

            wm_class = ""
            try:
                result2 = await self._run_cmd("xdotool getactivewindow")
                win_id = result2[0].strip()
                if win_id:
                    result3 = await self._run_cmd(f"xprop -id {win_id} WM_CLASS")
                    wm_class = result3[0].strip()
            except Exception:
                pass

            return WindowTextResult(
                window_title=win_title,
                app_name=wm_class,
                text="",
                success=True,
            )
        except Exception as e:
            logger.warning("Linux window text extraction failed: %s", e)
            return WindowTextResult(success=False)

    async def has_blocking_dialog(self, target_app_names: list[str] | None = None) -> bool:
        """Check if there is an OS-level dialog window blocking the target application.

        On Linux (X11), we check if the active window has _NET_WM_WINDOW_TYPE_DIALOG.
        """
        try:
            result = await self._run_cmd("xdotool getactivewindow")
            win_id = result[0].strip()
            if not win_id:
                return False

            result2 = await self._run_cmd(f"xprop -id {win_id} _NET_WM_WINDOW_TYPE")
            prop_out = result2[0].strip()

            has_dialog = "_NET_WM_WINDOW_TYPE_DIALOG" in prop_out
            if not has_dialog:
                return False

            if target_app_names:
                # We need to check if the dialog belongs to the target app
                # This is an approximation based on WM_CLASS
                result3 = await self._run_cmd(f"xprop -id {win_id} WM_CLASS")
                wm_class = result3[0].strip().lower()
                if not any(target.lower() in wm_class for target in target_app_names):
                    return False

            return True
        except Exception as e:
            logger.debug("Linux has_blocking_dialog check failed: %s", e)
            return False

    async def is_browser_active(self) -> bool:
        """Check if the currently active (frontmost) window is a web browser."""
        try:
            from myrm_agent_harness.toolkits.computer_use.types import KNOWN_BROWSER_NAMES

            result = await self._run_cmd("xdotool getactivewindow")
            win_id = result[0].strip()
            if not win_id:
                return False

            result2 = await self._run_cmd(f"xprop -id {win_id} WM_CLASS")
            wm_class = result2[0].strip().lower()

            return any(browser in wm_class for browser in KNOWN_BROWSER_NAMES)
        except Exception:
            return False

    def is_screen_locked(self) -> bool:
        from myrm_agent_harness.toolkits.computer_use.screen_detector import get_default_screen_detector

        return get_default_screen_detector().is_locked()

    def is_display_asleep(self) -> bool:
        from myrm_agent_harness.toolkits.computer_use.screen_detector import get_default_screen_detector

        return get_default_screen_detector().get_state() == ScreenLockState.SLEEPING

    async def check_permissions(self, *, probe_capture: bool = False) -> PermissionStatus:
        """Probe Linux environment readiness for desktop automation."""
        return await linux_permission_status(probe_capture=probe_capture)
