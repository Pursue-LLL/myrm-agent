"""Linux backend — scrot/gnome-screenshot + xdotool.

Covers both native Linux desktops and SaaS sandbox environments (which run Linux).

[INPUT]
- types::ScreenInfo, ScreenContext, ActionResult, WindowTextResult (POS: shared type definitions)
- linux_probes::probe_linux_capturable, detect_linux_resolution (POS: read-only screen probes)

[OUTPUT]
- LinuxBackend: ComputerBackend implementation for Linux

[POS]
Linux-specific screen I/O. Loaded for detect_platform().os_type == "linux".
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.computer_use.backends.linux_probes import (
    detect_linux_resolution,
    probe_linux_capturable,
)
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

# 我们总是以 UTF-8 收发字节。xdotool 按所在 locale 解码，不是 UTF-8 时遇到第一个非 ASCII 字符就报错并中断，所以显式指定；
# 用 LC_ALL 而不是 LC_CTYPE，因为宿主若设了 LC_ALL（如 C），它的优先级高于 LC_CTYPE。
_UTF8_LOCALE = "LC_ALL=C.UTF-8"

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
        self._display_prefix = f"DISPLAY=:{self._display_num} " if self._display_num is not None else ""

    def _subprocess_env(self) -> dict[str, str] | None:
        """Environment for shell-less subprocess calls: an inline `DISPLAY=:N` there would become argv[0]."""
        if self._display_num is None:
            return None
        return {**os.environ, "DISPLAY": f":{self._display_num}"}

    async def _run_cmd(self, cmd: str, stdin: str | None = None) -> tuple[str, str, int]:
        """Run a shell command under the selected display and a UTF-8 locale; `stdin` is piped, not put on the command line."""
        full_cmd = f"{_UTF8_LOCALE} {self._display_prefix}{cmd}"
        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(stdin.encode("utf-8") if stdin is not None else None)
        return stdout.decode(), stderr.decode(), proc.returncode or 0

    async def _run_input(self, cmd: str, stdin: str | None = None) -> None:
        """Run an input-injection command; a non-zero exit (e.g. xdotool missing) must not look like success."""
        _, stderr, code = await self._run_cmd(cmd, stdin)
        if code != 0:
            raise RuntimeError(f"{cmd.split()[0]} failed (exit {code}): {stderr.strip()}")

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

    async def _xdotool_type(self, text: str, delay_ms: int) -> None:
        """Type text through xdotool. It goes over stdin: out of the process list and independent of shell quoting."""
        await self._run_input(f"xdotool type --delay {delay_ms} --file -", stdin=text)

    async def type_text(self, text: str, delay_ms: int = 12, chunk_size: int = 50) -> ActionResult:
        """Type text (any script) as key events, in chunks so a long text is not one uninterruptible call."""
        try:
            for i in range(0, len(text), chunk_size):
                await self._xdotool_type(text[i : i + chunk_size], delay_ms)
            return ActionResult(success=True)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    async def type_credential(self, label: str) -> ActionResult:
        """Type a credential (password or TOTP) securely from the CredentialVault."""
        from myrm_agent_harness.core.security.credential_vault import get_global_credential_vault

        vault = get_global_credential_vault()

        is_totp = label.endswith("-totp")
        try:
            if is_totp:
                secret_text = vault.get_totp_token(label)
            else:
                secret_text = vault.get_password(label)
        except Exception:
            return ActionResult(success=False, error=f"Failed to retrieve credential for label '{label}'")

        try:
            # 凭据不进命令行参数（进程列表可见），也不经剪贴板。
            await self._xdotool_type(secret_text, 12)
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
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                env=self._subprocess_env(),
                capture_output=True,
                text=True,
                timeout=2,
            )
            window_title = result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            window_title = ""

        try:
            result = subprocess.run(
                ["xdotool", "getmouselocation"],
                env=self._subprocess_env(),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                mx = int(parts[0].split(":")[1])
                my = int(parts[1].split(":")[1])
            else:
                mx, my = 0, 0
        except Exception:
            mx, my = 0, 0

        return ScreenContext(active_window=window_title, mouse_x=mx, mouse_y=my)

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
        """Probe Linux environment readiness for desktop automation.

        Checks hard dependencies: xdotool (input), scrot/gnome-screenshot (capture),
        and DISPLAY/Wayland. Optional functional capture when probe_capture=True.
        """
        has_xdotool = shutil.which("xdotool") is not None
        has_screenshot = shutil.which("scrot") is not None or shutil.which("gnome-screenshot") is not None
        has_display = bool(os.getenv("DISPLAY"))
        wayland = bool(os.getenv("WAYLAND_DISPLAY"))

        deeplinks: dict[str, str] = {}
        if not has_xdotool:
            deeplinks["accessibility"] = "https://wiki.gnome.org/Accessibility"
        if not has_screenshot:
            deeplinks["screen_recording"] = "https://wiki.gnome.org/Accessibility"
        if not has_display and not wayland:
            deeplinks["display"] = "export DISPLAY=:0"
            if shutil.which("Xvfb") is None and shutil.which("xvfb-run") is None:
                deeplinks["xvfb"] = "Install Xvfb or use a graphical session"

        accessibility = has_xdotool and (has_display or wayland)
        screen_recording = has_screenshot and (has_display or wayland)
        capturable: bool | None = None
        if probe_capture:
            capturable = False
            if screen_recording and has_display:
                capturable = await asyncio.to_thread(probe_linux_capturable)

        return PermissionStatus(
            accessibility=accessibility,
            screen_recording=screen_recording,
            screen_recording_capturable=capturable,
            platform="linux",
            settings_deeplinks=deeplinks,
        )
