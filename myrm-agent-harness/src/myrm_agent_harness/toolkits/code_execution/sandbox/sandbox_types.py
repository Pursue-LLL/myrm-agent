"""Core types for OS-level process sandboxing.

[INPUT]  (none — pure type definitions)
[OUTPUT] SandboxPolicy, SandboxMode, SandboxProvider protocol, SandboxStatus, movable_ancestors
[POS]    Foundation layer — all sandbox modules import from here.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from typing import Protocol, runtime_checkable


class SandboxMode(StrEnum):
    """Sandbox activation strategy.

    AUTO:    detect environment capabilities; enable if available, skip in containers.
    ENABLE:  force-enable; raise if no provider available.
    DISABLE: never sandbox (NullProvider).
    """

    AUTO = "auto"
    ENABLE = "enable"
    DISABLE = "disable"


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Declarative sandbox restrictions applied at the OS level.

    writable_paths: directories the sandboxed process may write to, besides the provider's scratch
                    areas such as ``/tmp``. Everything else, including the working directory unless
                    it is listed here, is read-only or inaccessible.
    readable_paths: additional read-only bind-mounts (beyond default / ro-bind).
    read_only_subpaths: paths below a writable path that stay read-only. The process can neither modify,
                    replace nor remove them, and no directory above one of them (below the writable path)
                    can be renamed or recreated either, so a protected path cannot be moved away, edited
                    and moved back, or shadowed. Enforced by seatbelt and bwrap; AppContainer does not
                    enforce it.
    allow_network:  whether outbound network is permitted.
    env_passthrough: env var names forwarded into the sandbox.
    """

    writable_paths: tuple[str, ...] = ()
    readable_paths: tuple[str, ...] = ()
    read_only_subpaths: tuple[str, ...] = ()
    allow_network: bool = True
    env_passthrough: tuple[str, ...] = (
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "TERM",
        "SHELL",
        "TMPDIR",
    )

    def is_writable(self, path: str) -> bool:
        """Whether ``path`` lies inside one of ``writable_paths``."""
        target = PurePath(path)
        return any(target.is_relative_to(root) for root in self.writable_paths)


def movable_ancestors(path: str, writable_areas: Iterable[str]) -> list[str]:
    """Directories above ``path`` that lie strictly inside one of ``writable_areas``, nearest first.

    The process can rename each of them: it moves one away, changes what it held under the new name and moves it
    back, which defeats a rule that protects ``path`` only by name. An area root itself is not listed, it sits
    in a parent the process cannot write.
    """
    areas = tuple(area.rstrip(os.sep) + os.sep for area in writable_areas)
    movable: list[str] = []
    directory = os.path.dirname(path)
    while directory != os.path.dirname(directory):
        if any(directory.startswith(area) for area in areas):
            movable.append(directory)
        directory = os.path.dirname(directory)
    return movable


@dataclass(frozen=True, slots=True)
class SandboxStatus:
    """Runtime status of the sandbox layer."""

    enabled: bool
    provider_name: str
    reason: str = ""


@runtime_checkable
class SandboxProvider(Protocol):
    """OS-level sandbox provider (pluggable).

    Implementations wrap a shell command so that it executes inside an
    OS-level sandbox (bwrap, sandbox-exec, etc.).  The provider is called
    once when creating the persistent session process — all subsequent
    commands within that session inherit the restrictions.
    """

    @property
    def name(self) -> str:
        """Human-readable provider name (e.g. 'bwrap', 'seatbelt')."""
        ...

    def wrap_command(
        self,
        shell_path: str,
        shell_args: tuple[str, ...],
        work_dir: str,
        policy: SandboxPolicy,
    ) -> tuple[str, tuple[str, ...]]:
        """Return (executable, args) that launch *shell_path* inside a sandbox.

        The returned command replaces the direct shell invocation in
        ``LocalPersistentSession._create_process()``.
        """
        ...

    def is_available(self) -> bool:
        """Check whether this provider can run on the current system."""
        ...

    async def create_process(
        self,
        shell_path: str,
        shell_args: tuple[str, ...],
        work_dir: str,
        policy: SandboxPolicy,
        env: dict[str, str],
    ) -> asyncio.subprocess.Process | None:
        """Create a sandboxed process using native OS APIs.

        Providers that require direct OS API access (e.g. Windows AppContainer)
        override this to bypass ``asyncio.create_subprocess_exec`` which cannot
        pass platform-specific security attributes.

        Returns None to indicate the caller should fall back to
        ``wrap_command()`` + ``create_subprocess_exec()``.
        """
        return None

    def cleanup(self) -> None:
        """Release OS-level sandbox resources, temporary handles, and security ACLs."""
        ...
