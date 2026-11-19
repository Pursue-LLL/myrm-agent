"""Native file operations mixin for LocalExecutor.

[INPUT]
infra.atomic_write::async_atomic_write (POS: Atomic file writing utility)
core.security.path::is_sensitive_file, is_protected_instruction_file, is_evidence_readonly_file (POS: path security domain)
core.security.path.pattern::first_matching_pattern (POS: Path pattern matching — single source of truth for glob-style path protection)
core.context_vars::protected_paths_var (POS: Foundation ContextVar registry)
toolkits.code_execution.executors.granted_roots::refuse_write_into_readonly_grant (POS: read-only directory grants refuse writes)
toolkits.code_execution.interceptor::trigger_destructive_action_hook (POS: timeout-guarded call of the host's execution interceptor)

[OUTPUT]
LocalFileOpsMixin: Mixin providing pathlib-based file I/O with a write guard that
refuses credential paths, persona instruction files, read-only evidence, the
active Goal's protected paths and directories granted read-only. An allowed
mutation (every write variant and delete) is reported to the interceptor before it happens.

[POS]
Native file operations for local executor. Provides zero-subprocess-overhead
file read/write/delete using pathlib, with the read-only directory grants
and the shared path-protection rules so sandbox writes agree with the file tools and
the shell pre-flight.
"""

from __future__ import annotations

import logging
import stat
from pathlib import Path
from typing import Protocol

from myrm_agent_harness.core.security.ocap import CapabilityAction, enforce_capability_access
from myrm_agent_harness.infra.atomic_write import async_atomic_write
from myrm_agent_harness.toolkits.code_execution.executors.granted_roots import refuse_write_into_readonly_grant
from myrm_agent_harness.toolkits.code_execution.executors.gunzip import gunzip_bounded
from myrm_agent_harness.toolkits.code_execution.interceptor import (
    trigger_destructive_action_hook,
)

logger = logging.getLogger(__name__)


def _current_session_id() -> str | None:
    """Resolve the chat id bound by the agent runtime, or None outside an agent turn.

    File writes are allowed outside an explicit agent context (e.g. CLI utilities);
    no snapshot hook fires there.
    """
    try:
        from myrm_agent_harness.core.context_vars import chat_id_var

        return chat_id_var.get().strip() or None
    except Exception:
        return None


class _FileOpsHost(Protocol):
    """What the file operations need from the executor they are mixed into.

    ``_guard_write`` is defined by the mixin itself; it is listed because the methods reach it through
    ``self: _FileOpsHost``.
    """

    @property
    def workspace_path(self) -> str: ...

    async def resolve_path(self, relative_path: str) -> str: ...

    def _log_context_file_access(self, resolved_path: str, success: bool = True) -> None: ...

    def _guard_write(self, resolved_path: str) -> None: ...


async def _prepare_mutation(host: _FileOpsHost, path: str, action_type: str) -> str:
    """Resolve the target of a file mutation, refuse it when a protection rule forbids it, and report it.

    The snapshot hook fires only for an allowed mutation, so a refused write is never snapshotted. It is a no-op
    outside an agent turn (no chat id is bound) and never blocks the mutation: the interceptor call enforces its
    own timeout.
    """
    safe = await host.resolve_path(path)
    host._guard_write(safe)
    await trigger_destructive_action_hook(
        workspace_path=host.workspace_path,
        action_type=action_type,
        payload={"path": safe, "session_id": _current_session_id()},
    )
    return safe


class LocalFileOpsMixin:
    """Mixin providing local file operations via pathlib (zero subprocess overhead).

    The host supplies the state described by ``_FileOpsHost``.
    """

    def _guard_write(self: _FileOpsHost, resolved_path: str) -> None:
        """Refuse a write that any protection rule forbids.

        Credential paths are refused outright. Evidence directories and the active
        Goal's protected paths are refused for writes, matching the ``VIEW`` bypass the
        file-operation validators grant so a report can still be read back. Persona
        instruction files are refused here rather than escalated to a human: this
        executor has no approval channel, and the file tools and the permission
        middleware both ask before allowing the same write, so declining is the
        fail-closed direction for a surface that cannot ask.
        """
        enforce_capability_access(CapabilityAction.WRITE, resolved_path)
        refuse_write_into_readonly_grant(resolved_path, self.workspace_path)

        from myrm_agent_harness.core.context_vars import protected_paths_var
        from myrm_agent_harness.core.security.path import (
            is_evidence_readonly_file,
            is_protected_instruction_file,
            is_sensitive_file,
        )
        from myrm_agent_harness.core.security.path.pattern import first_matching_pattern

        matched = first_matching_pattern(resolved_path, protected_paths_var.get())
        if matched is not None:
            raise PermissionError(
                f"Write denied: '{resolved_path}' is protected by the active Goal (pattern: '{matched}')."
            )
        if is_evidence_readonly_file(resolved_path):
            raise PermissionError(
                f"Write denied: '{resolved_path}' is read-only session evidence. "
                f"Write derived output to 'artifacts/' instead."
            )
        if is_sensitive_file(resolved_path):
            raise PermissionError(f"Write denied: '{resolved_path}' matches a credential path rule.")
        if is_protected_instruction_file(resolved_path):
            raise PermissionError(
                f"Write denied: '{resolved_path}' is a persona instruction file. "
                f"Use file_write_tool so the write can be routed through approval."
            )

    async def read_file(self: _FileOpsHost, path: str) -> str:
        safe = await self.resolve_path(path)
        enforce_capability_access(CapabilityAction.READ, safe)
        self._log_context_file_access(safe, success=True)
        p = Path(safe)
        if not p.exists():
            self._log_context_file_access(safe, success=False)
            raise FileNotFoundError(f"File not found: {path}")

        if safe.endswith(".gz"):
            return gunzip_bounded(p.read_bytes()).decode("utf-8")

        # Bytes, not ``read_text``: text mode turns CRLF and lone CR into LF, and an edit would then write the file back
        # with every line ending changed.
        return p.read_bytes().decode("utf-8")

    async def file_size(self: _FileOpsHost, path: str) -> int:
        safe = await self.resolve_path(path)
        enforce_capability_access(CapabilityAction.READ, safe)
        try:
            st = Path(safe).stat()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}") from None
        if not stat.S_ISREG(st.st_mode):
            raise OSError(f"Not a regular file: {path}")
        return st.st_size

    async def read_file_bytes(self: _FileOpsHost, path: str) -> bytes:
        safe = await self.resolve_path(path)
        enforce_capability_access(CapabilityAction.READ, safe)
        p = Path(safe)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return p.read_bytes()

    async def write_file(self: _FileOpsHost, path: str, content: str) -> None:
        safe = await _prepare_mutation(self, path, "file_write")
        p = Path(safe)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Bytes, not ``write_text``: text mode writes ``\n`` as ``\r\n`` on Windows, which would turn a CRLF text into
        # CR CR LF.
        p.write_bytes(content.encode("utf-8"))

    async def write_file_bytes(self: _FileOpsHost, path: str, content: bytes) -> None:
        safe = await _prepare_mutation(self, path, "file_write")
        p = Path(safe)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    async def write_file_atomic(self: _FileOpsHost, path: str, content: str) -> None:
        safe = await _prepare_mutation(self, path, "file_write")
        await async_atomic_write(safe, content)

    async def write_file_bytes_atomic(self: _FileOpsHost, path: str, content: bytes) -> None:
        safe = await _prepare_mutation(self, path, "file_write")
        await async_atomic_write(safe, content)

    async def delete_file(self: _FileOpsHost, path: str) -> None:
        safe = await _prepare_mutation(self, path, "file_delete")
        Path(safe).unlink(missing_ok=True)

    async def file_exists(self: _FileOpsHost, path: str) -> bool:
        safe = await self.resolve_path(path)
        return Path(safe).exists()

    async def is_dir(self: _FileOpsHost, path: str) -> bool:
        safe = await self.resolve_path(path)
        return Path(safe).is_dir()

    async def list_files(self: _FileOpsHost, path: str = ".", pattern: str = "*") -> list[str]:
        safe = await self.resolve_path(path)
        return [str(f) for f in Path(safe).glob(pattern) if f.is_file()]
