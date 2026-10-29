"""Linux 屏幕探测 — 截图能力的功能探测与分辨率检测。

[INPUT]
- capture_probe::png_bytes_look_capturable (POS: 截图结果是否像真实画面的判定)

[OUTPUT]
- probe_linux_capturable: 用 scrot / gnome-screenshot 实际截一张图并判定是否可用
- detect_linux_resolution: 经 xdpyinfo / xrandr 读取屏幕分辨率，读不到回退 1920x1080

[POS]
Linux 后端的只读探测原语。仅被 backends/linux.py 引用；不发输入事件、不碰剪贴板。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


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
