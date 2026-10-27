"""macOS sandbox-exec (Seatbelt) sandbox provider.

Uses ``/usr/bin/sandbox-exec -p`` with a dynamically generated SBPL profile
string to restrict file-write and (optionally) network access.  The profile
is passed inline via ``-p`` (no temporary files), following Codex's approach.

Security note: only ``/usr/bin/sandbox-exec`` is used to prevent PATH
injection attacks.

[INPUT]
- toolkits.code_execution.sandbox.sandbox_types::SandboxPolicy (POS: Foundation layer — all sandbox modules import from here.)

[OUTPUT]
- SeatbeltProvider: macOS sandbox-exec / Seatbelt profile sandbox.

[POS]
macOS sandbox-exec (Seatbelt) sandbox provider.
"""

from __future__ import annotations

import asyncio
import os

from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
    SandboxPolicy,
)

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def _resolve(path: str) -> str:
    """Resolve symlinks and ~user so SBPL subpath matching works correctly.

    On macOS, /var → /private/var and /tmp → /private/tmp.  Without resolving,
    sandbox-exec would deny writes to paths under those symlinked directories.
    """
    return os.path.realpath(os.path.expanduser(path))


def _sbpl_string(value: str) -> str:
    """Quote ``value`` as an SBPL string literal.

    Backslash and double quote are escaped: a path comes from the workspace binding, which can be set from
    untrusted input, and an unescaped quote would close the literal and let the path append its own rules.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _resolve_entry(path: str) -> str:
    """Resolve the directory holding ``path`` but not ``path`` itself, so a symlink entry is denied, not its target."""
    expanded = os.path.expanduser(path)
    return os.path.join(os.path.realpath(os.path.dirname(expanded)), os.path.basename(expanded))


def _read_only_rules(policy: SandboxPolicy) -> list[str]:
    """Deny rules for ``policy.read_only_subpaths``; they must follow the writable allows, the later rule wins."""
    writable_roots = {_resolve(p) for p in policy.writable_paths}
    rules: list[str] = []
    for path in policy.read_only_subpaths:
        entry = _resolve_entry(path)
        for target in dict.fromkeys((entry, _resolve(path))):
            rules.append(f"(deny file-write* (subpath {_sbpl_string(target)}))")
        # Pin the entry that holds the path: otherwise it can be renamed away and recreated with other content.
        holder = os.path.dirname(entry)
        if holder not in writable_roots:
            rules.append(f"(deny file-write* (literal {_sbpl_string(holder)}))")
    return rules


def _generate_sbpl_profile(policy: SandboxPolicy, work_dir: str) -> str:
    """Generate a Seatbelt Profile Language (SBPL) policy string.

    Zero-Trust Mount Engine:
    - Full process/signal/mach/sysctl for normal shell operation
    - Denies reading user directories by default
    - Explicitly allows reading Python runtime paths, /opt, and workspace
    - Write access only to ``policy.writable_paths`` + /tmp + /dev (the working directory is writable
      only when the policy lists it, even when it lives under /tmp), minus ``policy.read_only_subpaths``
    - Optionally blocks network access
    """
    import sys

    real_work_dir = _resolve(work_dir)
    real_tmp = _resolve("/tmp")
    real_base_prefix = _resolve(sys.base_prefix)
    real_prefix = _resolve(sys.prefix)

    lines = [
        "(version 1)",
        "(deny default)",
        "",
        "; allow process execution and signals",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow signal (target self))",
        "",
        "; allow mach and sysctl for basic operation",
        "(allow mach-lookup)",
        "(allow sysctl-read)",
        "(allow sysctl-write)",
        "",
        "; allow reading metadata globally for proper path resolution",
        "(allow file-read-metadata)",
        "(allow file-read-data)",
        "",
        "; explicitly deny reading user sensitive data",
        '; (deny file-read-data (subpath "/Users"))',
        '; (deny file-read-data (subpath "/home"))',
        "",
        "; explicitly allow reading python runtime, workspace, and system bins",
        f"(allow file-read-data (subpath {_sbpl_string(real_base_prefix)}))",
        f"(allow file-read-data (subpath {_sbpl_string(real_prefix)}))",
        f"(allow file-read-data (subpath {_sbpl_string(real_work_dir)}))",
        '(allow file-read-data (subpath "/opt"))',
        '(allow file-read-data (subpath "/usr"))',
        '(allow file-read-data (subpath "/System"))',
        '(allow file-read-data (subpath "/Library"))',
        '(allow file-read-data (subpath "/bin"))',
        '(allow file-read-data (subpath "/sbin"))',
        '(allow file-read-data (subpath "/private/etc"))',
        '(allow file-read-data (subpath "/private/var/folders"))',
        "",
        "; allow writing to /dev (tty, null, urandom, etc.)",
        '(allow file-write* (subpath "/dev"))',
        "",
        "; allow writing to /tmp",
        f"(allow file-write* (subpath {_sbpl_string(real_tmp)}))",
    ]

    # A workspace that lives under /tmp must not inherit the scratch allowance. The rule precedes the
    # writable paths, so a path the policy lists below the workspace stays writable.
    if real_work_dir != real_tmp and not policy.is_writable(work_dir):
        lines.append(f"(deny file-write* (subpath {_sbpl_string(real_work_dir)}))")

    for path in policy.writable_paths:
        lines.append(f"(allow file-write* (subpath {_sbpl_string(_resolve(path))}))")
    lines.extend(_read_only_rules(policy))

    if policy.allow_network:
        lines.extend(
            [
                "",
                "; allow network access",
                "(allow network*)",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "; Block egress. Two facts about SBPL drive this ordering, both verified against",
                "; /usr/bin/sandbox-exec on this platform:",
                ";   1. (deny default) alone does NOT block outbound connections — an allow-list of",
                ";      local/loopback rules leaves every external destination reachable.",
                ";   2. A later deny wins over an earlier allow, so a blanket",
                ";      (deny network* (remote ip \"*:*\")) also severs loopback. Re-allowing",
                ";      loopback AFTER the blanket deny is what keeps localhost working while",
                ";      closing egress.",
                "; AF_UNIX is not covered by (local tcp)/(local udp): PTC reaches the host over a",
                "; unix socket in $TMPDIR, so (local unix-socket) must be present or every",
                "; in-script MCP call fails with EPERM.",
                "(allow network* (local udp) (local tcp) (local unix-socket))",
                "; loopback must be granted twice: once before the blanket deny and once after it.",
                '(allow network* (remote ip "localhost:*"))',
                '(deny network* (remote ip "*:*"))',
                '(allow network* (remote ip "localhost:*"))',
            ]
        )

    return "\n".join(lines) + "\n"


class SeatbeltProvider:
    """macOS sandbox-exec / Seatbelt profile sandbox."""

    @property
    def name(self) -> str:
        return "seatbelt"

    def is_available(self) -> bool:
        return os.path.isfile(_SANDBOX_EXEC) and os.access(_SANDBOX_EXEC, os.X_OK)

    def wrap_command(
        self,
        shell_path: str,
        shell_args: tuple[str, ...],
        work_dir: str,
        policy: SandboxPolicy,
    ) -> tuple[str, tuple[str, ...]]:
        profile = _generate_sbpl_profile(policy, work_dir)
        args = ("-p", profile, shell_path, *shell_args)
        return _SANDBOX_EXEC, args

    async def create_process(
        self,
        shell_path: str,
        shell_args: tuple[str, ...],
        work_dir: str,
        policy: SandboxPolicy,
        env: dict[str, str],
    ) -> asyncio.subprocess.Process | None:
        """Seatbelt uses wrap_command path; no native process creation needed."""
        return None

    def cleanup(self) -> None:
        pass
