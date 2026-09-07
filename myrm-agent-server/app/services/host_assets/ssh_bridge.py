"""Secure SSH remote command execution bridge service.

[INPUT]
- asyncio, time, typing.Callable, typing.Optional
- .models::HostAssetConfig, SSHCommandRequest, SSHCommandResult
- .vault::HostAssetVault

[OUTPUT]
- SSHOpsBridge, SSHRemoteExecutionError

[POS]
Domain service in app/services/host_assets/ executing commands on managed remote hosts.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Awaitable, Callable, Optional

from app.services.host_assets.models import (
    HostAssetConfig,
    SSHCommandRequest,
    SSHCommandResult,
)
from app.services.host_assets.vault import HostAssetVault

# High-risk command pattern for defense-in-depth safety
_HIGH_RISK_PATTERN = re.compile(
    r"(?:\brm\s+-rf\s+[/~]|\bmkfs\b|\bdd\s+if=|\b:(){ :\|:& };:)",
    re.IGNORECASE,
)


class SSHRemoteExecutionError(Exception):
    """Raised when remote SSH execution encounters unrecoverable failure."""


class SSHOpsBridge:
    """Safe SSH execution bridge for remote host assets."""

    def __init__(self, vault: HostAssetVault) -> None:
        self._vault = vault

    async def execute_command(
        self,
        request: SSHCommandRequest,
        mock_runner: Optional[
            Callable[
                [HostAssetConfig, str, float],
                Awaitable[tuple[int, str, str]],
            ]
        ] = None,
    ) -> SSHCommandResult:
        """Execute a remote command on the specified host asset.

        Args:
            request: The command execution request with host_id and command.
            mock_runner: Optional test hook for mocking remote execution.
        """
        start_time = time.perf_counter()
        host = self._vault.get_host(request.host_id)
        if not host:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return SSHCommandResult(
                host_id=request.host_id,
                command=request.command,
                exit_code=1,
                stdout="",
                stderr=f"Host asset '{request.host_id}' not found in vault",
                duration_ms=duration_ms,
                success=False,
            )

        # Safety gate: block catastrophic destructive commands
        if _HIGH_RISK_PATTERN.search(request.command):
            duration_ms = (time.perf_counter() - start_time) * 1000
            return SSHCommandResult(
                host_id=request.host_id,
                command=request.command,
                exit_code=126,
                stdout="",
                stderr="Execution blocked by safety policy: High-risk destructive command pattern detected",
                duration_ms=duration_ms,
                success=False,
            )

        if mock_runner is not None:
            try:
                exit_code, stdout, stderr = await asyncio.wait_for(
                    mock_runner(host, request.command, request.timeout_seconds),
                    timeout=request.timeout_seconds,
                )
            except asyncio.TimeoutError:
                duration_ms = (time.perf_counter() - start_time) * 1000
                return SSHCommandResult(
                    host_id=request.host_id,
                    command=request.command,
                    exit_code=124,
                    stdout="",
                    stderr=f"Command execution timed out after {request.timeout_seconds}s",
                    duration_ms=duration_ms,
                    success=False,
                )
            except Exception as exc:  # noqa: BLE001
                duration_ms = (time.perf_counter() - start_time) * 1000
                return SSHCommandResult(
                    host_id=request.host_id,
                    command=request.command,
                    exit_code=1,
                    stdout="",
                    stderr=f"Remote execution error: {exc}",
                    duration_ms=duration_ms,
                    success=False,
                )
        else:
            # Default production path using system ssh client invocation
            cmd_args = ["ssh", "-p", str(host.port), "-o", "BatchMode=yes"]
            if host.private_key_path:
                cmd_args.extend(["-i", host.private_key_path])

            target = f"{host.username}@{host.hostname}"
            cmd_args.extend([target, request.command])

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=request.timeout_seconds
                )
                exit_code = process.returncode or 0
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                duration_ms = (time.perf_counter() - start_time) * 1000
                return SSHCommandResult(
                    host_id=request.host_id,
                    command=request.command,
                    exit_code=124,
                    stdout="",
                    stderr=f"Command execution timed out after {request.timeout_seconds}s",
                    duration_ms=duration_ms,
                    success=False,
                )
            except Exception as exc:  # noqa: BLE001
                duration_ms = (time.perf_counter() - start_time) * 1000
                return SSHCommandResult(
                    host_id=request.host_id,
                    command=request.command,
                    exit_code=1,
                    stdout="",
                    stderr=f"SSH transport invocation error: {exc}",
                    duration_ms=duration_ms,
                    success=False,
                )

        duration_ms = (time.perf_counter() - start_time) * 1000
        return SSHCommandResult(
            host_id=request.host_id,
            command=request.command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            success=(exit_code == 0),
        )
