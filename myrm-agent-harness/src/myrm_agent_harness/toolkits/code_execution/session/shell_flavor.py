"""Platform-specific shell behavior drivers.

[INPUT]
platform::PlatformInfo (POS: OS detection and shell path resolution)

[OUTPUT]
ShellFlavor: ABC for platform-specific shell command formatting; applies a command's ``CommandEnv`` around it.
BashFlavor: Bash/POSIX shell driver with ulimit init, exit() interceptor, and block-rc command wrapping.
PowerShellFlavor: Windows PowerShell driver with UTF-8 encoding, Progress suppression, exit() interceptor, and dual exit code normalization.
WindowsFlavor: Legacy Windows cmd driver.
get_flavor: Factory returning the appropriate flavor for the platform.

[POS]
Platform-specific shell command formatting. Encapsulates differences between
Bash, PowerShell, and Windows cmd for command wrapping, env injection, and init sequences.
"""

from __future__ import annotations

import logging
import re
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.shell_quote import (
    windows_cmd_quote,
    windows_powershell_quote,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from myrm_agent_harness.toolkits.code_execution.platform import PlatformInfo
    from myrm_agent_harness.toolkits.code_execution.session.models import CommandEnv

logger = logging.getLogger(__name__)

# A name is spliced into shell text unquoted, so only plain identifiers may pass.
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

# PowerShell reads all four of these as a single quote, so each one is doubled inside a literal.
_POWERSHELL_SINGLE_QUOTES = "'\u2018\u2019\u201a\u201b"


class ShellFlavor(ABC):
    """Platform-specific shell behavior driver."""

    @abstractmethod
    def build_init_commands(self, work_dir: str, timeout: int, max_memory_mb: int) -> list[str]: ...

    @abstractmethod
    def format_env_set(self, key: str, value: str) -> str: ...

    @abstractmethod
    def format_env_unset(self, key: str) -> str: ...

    @abstractmethod
    def build_wrapped_command(
        self, command: str, exit_marker: str, end_marker: str, exit_code_var: str, env: CommandEnv | None = None
    ) -> str: ...

    def env_commands(self, env: CommandEnv | None) -> tuple[list[str], list[str]]:
        """Return the lines that set ``env`` before a command and those that clear its scoped values after it."""
        if env is None:
            return [], []
        sticky = _valid_env_names(env.sticky)
        scoped = _valid_env_names(env.scoped)
        set_lines = [self.format_env_set(name, value) for name, value in {**sticky, **scoped}.items()]
        return set_lines, [self.format_env_unset(name) for name in scoped]


def _powershell_literal(value: str) -> str:
    """Return ``value`` as a verbatim single-quoted PowerShell string.

    Always quoted: after ``=`` a bare word is run as a command, so an unquoted plain token would never be assigned.
    """
    return "'" + "".join(char * 2 if char in _POWERSHELL_SINGLE_QUOTES else char for char in value) + "'"


def _valid_env_names(env: Mapping[str, str]) -> dict[str, str]:
    """Return ``env`` without the entries whose name could not be spliced into shell text safely."""
    valid = {name: value for name, value in env.items() if _ENV_NAME.match(name)}
    for name in env.keys() - valid.keys():
        logger.warning("Environment entry skipped: %r is not a plain variable name", name)
    return valid


class BashFlavor(ShellFlavor):
    def build_init_commands(self, work_dir: str, timeout: int, max_memory_mb: int) -> list[str]:
        memory_kb = max_memory_mb * 1024
        cpu_limit = max(600, timeout * 5)

        # On macOS, ulimit -v can cause simple forks to fail due to large
        # shared system cache VM sizes. Also ulimit -u on macOS applies per
        # user, so 512 is too low for a developer machine.
        if sys.platform == "darwin":
            ulimit_cmd = f"ulimit -t {cpu_limit} 2>/dev/null || true"
        else:
            ulimit_cmd = f"ulimit -t {cpu_limit} -v {memory_kb} -u 512 2>/dev/null || true"

        return [
            "set +o history 2>/dev/null || true",
            "export PS1='' PS2='' NO_COLOR=1 FORCE_COLOR=0 TERM=dumb",
            # Contain `exit` inside the command block so a trailing `exit N`
            # from an LLM-generated command returns from the block instead of
            # killing the persistent shell (which would silently lose cwd/env).
            "exit() { builtin return $(( ${1:-0} )); }",
            f"cd '{work_dir}' || cd /tmp",
            ulimit_cmd,
        ]

    def format_env_set(self, key: str, value: str) -> str:
        # ANSI-C quoting ($'...') keeps $, backticks and double quotes
        # literal and escapes control chars (\n\r\t) to single-line
        # sequences, so an env value can never break the init batch or let
        # the shell re-expand injected tokens. Backslash is doubled first so
        # existing escape sequences survive verbatim.
        escaped = (
            value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f"export {key}=$'{escaped}'"

    def format_env_unset(self, key: str) -> str:
        return f"unset {key}"

    def build_wrapped_command(
        self, command: str, exit_marker: str, end_marker: str, exit_code_var: str, env: CommandEnv | None = None
    ) -> str:
        # EXIT trap backs up the marker pair so an errexit crash (e.g. `set -e`
        # failing) still emits a parseable boundary. `set -e` is a bash-native
        # "fail fast" that terminates the shell — without the trap the process
        # dies markerless, the session reads EOF and misreports an unexpected
        # crash (triggering a pointless recovery). The trap only fires when the
        # shell actually exits; a healthy command leaves it dormant so markers
        # are emitted exactly once per execution.
        #
        # The command's variables are exported inside the block, so the command sees them in the persistent shell
        # itself. The scoped ones are unset after the end marker rather than inside the block: ``exit`` leaves the
        # block early, and nothing after the markers can change the exit code the caller reads.
        clean_command = command.rstrip("\r\n")
        set_lines, unset_lines = self.env_commands(env)
        return (
            f'trap \'echo "{exit_marker}"$?; echo "{end_marker}"\' EXIT\n'
            "{\n" + "".join(f"{line}\n" for line in set_lines) + f"{clean_command}\n"
            f"__myrm_rc__={exit_code_var}\n"
            "}\n"
            f"echo '{exit_marker}'\"$__myrm_rc__\"\n"
            f"echo '{end_marker}'\n" + "".join(f"{line}\n" for line in unset_lines)
        )


class PowerShellFlavor(ShellFlavor):
    """Windows PowerShell persistent session driver."""

    def build_init_commands(self, work_dir: str, timeout: int, max_memory_mb: int) -> list[str]:
        quoted_work_dir = windows_powershell_quote(work_dir)
        return [
            # Ensure full UTF-8 encoding for console in/out streams to eliminate mojibake
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; [Console]::InputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8;",
            # Suppress Write-Progress streams from polluting command stdout
            "$ProgressPreference = 'SilentlyContinue';",
            "$ErrorActionPreference = 'Continue';",
            # Clear interactive prompt string
            "function prompt { '' }",
            # Intercept exit calls from LLM scripts so they do not terminate the persistent session process
            "function exit { param([int]$code=0) return $code }",
            # Establish base working directory
            f"Set-Location -LiteralPath {quoted_work_dir}",
        ]

    def format_env_set(self, key: str, value: str) -> str:
        return f"$env:{key} = {_powershell_literal(value)}"

    def format_env_unset(self, key: str) -> str:
        return f"Remove-Item Env:{key} -ErrorAction SilentlyContinue"

    def build_wrapped_command(
        self, command: str, exit_marker: str, end_marker: str, exit_code_var: str, env: CommandEnv | None = None
    ) -> str:
        # Wrap command block, normalize exit codes between native exes ($LASTEXITCODE) and cmdlets ($?),
        # and emit unambiguous randomized boundary markers. Scoped variables are removed after the end marker so
        # the removal cannot disturb $LASTEXITCODE / $?.
        set_lines, unset_lines = self.env_commands(env)
        return (
            "".join(f"{line}\n" for line in set_lines) + "& {\n"
            f"{command}\n"
            "}\n"
            f"$__myrm_rc__ = if ($LASTEXITCODE -ne $null) {{ $LASTEXITCODE }} else {{ [int](-not $?) }}\n"
            f"Write-Output '{exit_marker}'$__myrm_rc__\n"
            f"Write-Output '{end_marker}'\n" + "".join(f"{line}\n" for line in unset_lines)
        )


class WindowsFlavor(ShellFlavor):
    def build_init_commands(self, work_dir: str, timeout: int, max_memory_mb: int) -> list[str]:
        return ["@echo off", "prompt $G", f"cd /d {windows_cmd_quote(work_dir)}"]

    def format_env_set(self, key: str, value: str) -> str:
        # CMD environment variable setting with % escape and proper wrapping
        escaped_val = value.replace("%", "%%")
        return f"set {key}={escaped_val}"

    def format_env_unset(self, key: str) -> str:
        return f"set {key}="

    def build_wrapped_command(
        self, command: str, exit_marker: str, end_marker: str, exit_code_var: str, env: CommandEnv | None = None
    ) -> str:
        set_lines, unset_lines = self.env_commands(env)
        return (
            "".join(f"{line}\r\n" for line in set_lines)
            + f"{command}\r\necho {exit_marker}{exit_code_var}\r\necho {end_marker}\r\n"
            + "".join(f"{line}\r\n" for line in unset_lines)
        )


def get_flavor(platform_info: PlatformInfo) -> ShellFlavor:
    """Factory: return the appropriate shell flavor for the detected platform."""
    if platform_info.is_windows:
        if platform_info.shell_type == "powershell":
            return PowerShellFlavor()
        return WindowsFlavor()
    return BashFlavor()
