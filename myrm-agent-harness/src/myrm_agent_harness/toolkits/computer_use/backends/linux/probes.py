"""Linux 屏幕与环境探测 — 截图能力的功能探测、分辨率检测、屏幕上下文与环境就绪度。

[INPUT]
- capture_probe::png_bytes_look_capturable (POS: 截图结果是否像真实画面的判定)
- types::PermissionStatus, ScreenContext (POS: shared type definitions)

[OUTPUT]
- probe_linux_capturable: 用 scrot / gnome-screenshot 实际截一张图并判定是否可用
- detect_linux_resolution: 经 xdpyinfo / xrandr 读取屏幕分辨率，读不到回退 1920x1080
- read_screen_context: 经 xdotool 读活动窗口标题与鼠标位置，读不到的字段回退空串 / (0, 0)
- linux_permission_status: 按 xdotool、截图工具、DISPLAY / Wayland 是否齐备给出桌面自动化就绪度

[POS]
Linux 后端的只读探测原语。仅被 backends/linux/backend.py 引用；不发输入事件、不碰剪贴板。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.computer_use.types import PermissionStatus, ScreenContext


def probe_linux_capturable() -> bool:
    """Functional capture probe via scrot or gnome-screenshot."""
    from myrm_agent_harness.toolkits.computer_use.capture_probe import (
        png_bytes_look_capturable,
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        if shutil.which("scrot"):
            cmd = ["scrot", "-o", str(tmp_path)]
        elif shutil.which("gnome-screenshot"):
            cmd = ["gnome-screenshot", "-f", str(tmp_path)]
        else:
            return False
        result = subprocess.run(cmd, capture_output=True, timeout=1.5, check=False)
        if result.returncode != 0 or not tmp_path.is_file():
            return False
        return png_bytes_look_capturable(tmp_path.read_bytes())
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        tmp_path.unlink(missing_ok=True)


def detect_linux_resolution(env: dict[str, str] | None) -> tuple[int, int]:
    """Detect screen resolution via xdpyinfo or xrandr, run under `env` (None inherits the current environment)."""
    for cmd in ("xdpyinfo", "xrandr"):
        try:
            result = subprocess.run(
                [cmd],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if "dimensions:" in line:
                    parts = line.split("dimensions:")[1].strip().split()[0]
                    w, h = parts.split("x")
                    return int(w), int(h)
                if "*" in line and "x" in line:
                    parts = line.strip().split()[0]
                    w, h = parts.split("x")
                    return int(w.split(".")[0]), int(h.split(".")[0])
        except Exception:
            continue

    return 1920, 1080


def read_screen_context(env: dict[str, str] | None) -> ScreenContext:
    """Active window title and mouse position under `env` (None inherits the process environment).

    A field that cannot be read stays empty / (0, 0).
    """
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            env=env,
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
            env=env,
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


async def linux_permission_status(*, probe_capture: bool) -> PermissionStatus:
    """Readiness of the hard dependencies: xdotool (input), scrot/gnome-screenshot (capture), DISPLAY or Wayland.

    With `probe_capture`, a screenshot is actually taken to confirm capture works.
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
