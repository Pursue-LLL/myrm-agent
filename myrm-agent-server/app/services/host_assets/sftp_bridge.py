"""Secure SFTP remote file transfer bridge service.

[INPUT]
- asyncio, typing.Callable, typing.Optional
- .models::HostAssetConfig, SFTPReadRequest, SFTPTransferResult, SFTPWriteRequest
- .vault::HostAssetVault

[OUTPUT]
- SFTPBridge

[POS]
Domain service in app/services/host_assets/ facilitating remote file operations.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from app.services.host_assets.models import (
    HostAssetConfig,
    SFTPReadRequest,
    SFTPTransferResult,
    SFTPWriteRequest,
)
from app.services.host_assets.vault import HostAssetVault


class SFTPBridge:
    """Safe SFTP file transfer bridge for remote host assets."""

    def __init__(self, vault: HostAssetVault) -> None:
        self._vault = vault

    async def read_remote_file(
        self,
        request: SFTPReadRequest,
        mock_reader: Optional[
            Callable[
                [HostAssetConfig, str, int],
                Awaitable[tuple[bool, Optional[str], int, Optional[str]]],
            ]
        ] = None,
    ) -> SFTPTransferResult:
        """Read content from a remote file via SFTP/SSH.

        Args:
            request: SFTP read request payload.
            mock_reader: Optional mock hook returning (success, content, bytes_transferred, error).
        """
        host = self._vault.get_host(request.host_id)
        if not host:
            return SFTPTransferResult(
                host_id=request.host_id,
                remote_path=request.remote_path,
                success=False,
                error=f"Host asset '{request.host_id}' not found in vault",
            )

        if mock_reader is not None:
            try:
                success, content, bytes_read, error = await mock_reader(
                    host, request.remote_path, request.max_bytes
                )
                return SFTPTransferResult(
                    host_id=request.host_id,
                    remote_path=request.remote_path,
                    success=success,
                    content=content,
                    bytes_transferred=bytes_read,
                    error=error,
                )
            except Exception as exc:  # noqa: BLE001
                return SFTPTransferResult(
                    host_id=request.host_id,
                    remote_path=request.remote_path,
                    success=False,
                    error=f"SFTP read error: {exc}",
                )

        # Default fallback via ssh cat
        cmd_args = ["ssh", "-p", str(host.port), "-o", "BatchMode=yes"]
        if host.private_key_path:
            cmd_args.extend(["-i", host.private_key_path])

        target = f"{host.username}@{host.hostname}"
        cmd_args.extend([target, f"cat {request.remote_path}"])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=30.0
            )
            if process.returncode != 0:
                err_msg = stderr_bytes.decode("utf-8", errors="replace").strip()
                return SFTPTransferResult(
                    host_id=request.host_id,
                    remote_path=request.remote_path,
                    success=False,
                    error=err_msg or "Failed to read remote file",
                )

            trimmed = stdout_bytes[: request.max_bytes]
            text = trimmed.decode("utf-8", errors="replace")
            return SFTPTransferResult(
                host_id=request.host_id,
                remote_path=request.remote_path,
                success=True,
                content=text,
                bytes_transferred=len(trimmed),
            )
        except Exception as exc:  # noqa: BLE001
            return SFTPTransferResult(
                host_id=request.host_id,
                remote_path=request.remote_path,
                success=False,
                error=f"SFTP transport error: {exc}",
            )

    async def write_remote_file(
        self,
        request: SFTPWriteRequest,
        mock_writer: Optional[
            Callable[
                [HostAssetConfig, str, str, str],
                Awaitable[tuple[bool, int, Optional[str]]],
            ]
        ] = None,
    ) -> SFTPTransferResult:
        """Write content to a remote file via SFTP/SSH."""
        host = self._vault.get_host(request.host_id)
        if not host:
            return SFTPTransferResult(
                host_id=request.host_id,
                remote_path=request.remote_path,
                success=False,
                error=f"Host asset '{request.host_id}' not found in vault",
            )

        if mock_writer is not None:
            try:
                success, bytes_written, error = await mock_writer(
                    host, request.remote_path, request.content, request.mode
                )
                return SFTPTransferResult(
                    host_id=request.host_id,
                    remote_path=request.remote_path,
                    success=success,
                    bytes_transferred=bytes_written,
                    error=error,
                )
            except Exception as exc:  # noqa: BLE001
                return SFTPTransferResult(
                    host_id=request.host_id,
                    remote_path=request.remote_path,
                    success=False,
                    error=f"SFTP write error: {exc}",
                )

        # Default fallback via ssh tee
        redirect_op = ">>" if request.mode == "append" else ">"
        cmd_args = ["ssh", "-p", str(host.port), "-o", "BatchMode=yes"]
        if host.private_key_path:
            cmd_args.extend(["-i", host.private_key_path])

        target = f"{host.username}@{host.hostname}"
        cmd_args.extend([target, f"cat {redirect_op} {request.remote_path}"])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            input_bytes = request.content.encode("utf-8")
            _, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=input_bytes), timeout=30.0
            )
            if process.returncode != 0:
                err_msg = stderr_bytes.decode("utf-8", errors="replace").strip()
                return SFTPTransferResult(
                    host_id=request.host_id,
                    remote_path=request.remote_path,
                    success=False,
                    error=err_msg or "Failed to write remote file",
                )

            return SFTPTransferResult(
                host_id=request.host_id,
                remote_path=request.remote_path,
                success=True,
                bytes_transferred=len(input_bytes),
            )
        except Exception as exc:  # noqa: BLE001
            return SFTPTransferResult(
                host_id=request.host_id,
                remote_path=request.remote_path,
                success=False,
                error=f"SFTP write transport error: {exc}",
            )
