"""Cross-platform runtime detection and shell configuration.

Single source of truth for all platform-specific knowledge.
Other modules consume PlatformInfo instead of scattered ``if IS_WINDOWS`` checks.

Provides:
- WSL multi-layer detection (env vars → /proc/version)
- A safe environment variable whitelist per platform
- Shell configuration as data (shell_path, shell_args)

[INPUT]
- (none)

[OUTPUT]
- PlatformInfo: Immutable snapshot of host platform characteristics.
- detect_platform: Detect and cache the host platform info (singleton).

[POS]
Cross-platform runtime detection and shell configuration.
"""

from __future__ import annotations

import functools
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from typing import Literal

OSType = Literal["windows", "macos", "linux"]
ShellType = Literal["bash", "powershell", "cmd"]

_POSIX_SAFE_ENV_VARS: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "USER",
        "SHELL",
        "TMPDIR",
    }
)

_WINDOWS_SAFE_ENV_VARS: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "TERM",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "PATHEXT",
    }
)


def _detect_wsl() -> bool:
    """Detect Windows Subsystem for Linux via env vars then /proc/version."""
    if sys.platform != "linux":
        return False
    if any(os.environ.get(k) for k in ("WSL_INTEROP", "WSL_DISTRO_NAME", "WSLENV")):
        return True
    try:
        with open("/proc/version", encoding="utf-8") as f:
            release = f.read().lower()
        return "microsoft" in release or "wsl" in release
    except OSError:
        return False


@dataclass(frozen=True)
class PlatformInfo:
    """Immutable snapshot of host platform characteristics.

    All platform-specific decisions should be driven by fields on this object
    rather than by inspecting ``sys.platform`` at the call site.
    """

    os_type: OSType
    os_release: str
    arch: str
    is_wsl: bool

    shell_path: str
    shell_args: tuple[str, ...]
    shell_type: ShellType
    exit_code_var: str
    env_set_template: str
    path_separator: str
    process_group_creation_flag: int
    safe_env_vars: frozenset[str]

    @property
    def is_windows(self) -> bool:
        return self.os_type == "windows"

    @property
    def is_posix(self) -> bool:
        return self.os_type in ("macos", "linux")

    @property
    def prompt_label(self) -> str:
        """Human-readable OS description for the bash tool description."""
        names: dict[OSType, str] = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
        base = f"{names[self.os_type]} ({self.os_release}, {self.arch})"
        if self.is_wsl:
            base += " [WSL: Linux environment on Windows host]"
        return base

    @property
    def shell_hint(self) -> str:
        """Shell usage hints for the bash tool description."""
        if self.os_type == "macos":
            return "bash (BSD toolchain: use vm_stat instead of free, no GNU long options for ps/top)"
        if self.os_type == "windows":
            if self.shell_type == "powershell":
                return "powershell (PowerShell toolchain: use Get-ChildItem/Test-Path/Select-String or common aliases ls/cat/grep)"
            return "cmd.exe (use dir/type/tasklist instead of ls/cat/ps)"
        if self.is_wsl:
            return "bash (Linux on WSL, but host is Windows)"
        return "bash (GNU toolchain)"


@functools.lru_cache(maxsize=1)
def detect_platform() -> PlatformInfo:
    """Detect and cache the host platform info (singleton)."""
    system = platform.system().lower()

    if system == "darwin":
        os_type: OSType = "macos"
    elif system == "windows":
        os_type = "windows"
    else:
        os_type = "linux"

    is_wsl = _detect_wsl()

    if os_type == "windows":
        powershell_bin = (
            shutil.which("powershell.exe")
            or shutil.which("pwsh.exe")
            or shutil.which("powershell")
            or shutil.which("pwsh")
        )
        if powershell_bin:
            return PlatformInfo(
                os_type=os_type,
                os_release=platform.release(),
                arch=platform.machine(),
                is_wsl=False,
                shell_path=powershell_bin,
                shell_args=("-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"),
                shell_type="powershell",
                exit_code_var="$__myrm_rc__",
                env_set_template="$env:{key}={value}",
                path_separator=";",
                process_group_creation_flag=0x00000200,  # CREATE_NEW_PROCESS_GROUP
                safe_env_vars=_WINDOWS_SAFE_ENV_VARS,
            )

        return PlatformInfo(
            os_type=os_type,
            os_release=platform.release(),
            arch=platform.machine(),
            is_wsl=False,
            shell_path="cmd.exe",
            shell_args=("/Q",),
            shell_type="cmd",
            exit_code_var="%ERRORLEVEL%",
            env_set_template="set {key}={value}",
            path_separator=";",
            process_group_creation_flag=0x00000200,  # CREATE_NEW_PROCESS_GROUP
            safe_env_vars=_WINDOWS_SAFE_ENV_VARS,
        )

    return PlatformInfo(
        os_type=os_type,
        os_release=platform.release(),
        arch=platform.machine(),
        is_wsl=is_wsl,
        shell_path="/bin/bash",
        shell_args=("--norc", "--noprofile"),
        shell_type="bash",
        exit_code_var="$?",
        env_set_template="export {key}={value}",
        path_separator=":",
        process_group_creation_flag=0,
        safe_env_vars=_POSIX_SAFE_ENV_VARS,
    )
