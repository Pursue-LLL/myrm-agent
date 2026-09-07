"""SSH Connection Pool and Command Execution Pipeline.

[INPUT]
- .models::SSHHostAsset, SSHExecResult, HostConnectionStatus
- asyncio, time, logging

[OUTPUT]
- SSHConnectionPool: Manages remote host handshakes, probing, and execution dispatch.

[POS]
Domain service in app/services/ssh_bridge/pool.py.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from .models import HostConnectionStatus, SSHExecResult, SSHHostAsset

logger = logging.getLogger("myrm.services.ssh_bridge.pool")


class SSHConnectionPool:
    """Manages active SSH connections, health checking, and remote command execution."""

    def __init__(self, default_timeout_s: float = 30.0) -> None:
        self._default_timeout_s = default_timeout_s
        self._mock_driver: Optional[Callable[[SSHHostAsset, str], SSHExecResult]] = None

    def set_mock_driver(self, driver: Optional[Callable[[SSHHostAsset, str], SSHExecResult]]) -> None:
        """Inject custom driver for unit testing without physical remote network."""
        self._mock_driver = driver

    async def probe_host_health(self, host: SSHHostAsset) -> HostConnectionStatus:
        """Check whether remote host is reachable."""
        start_t = time.time()
        
        # If mock driver is registered, simulate fast probe
        if self._mock_driver:
            latency = (time.time() - start_t) * 1000.0 + 1.2
            return HostConnectionStatus(
                host_id=host.host_id,
                is_online=True,
                latency_ms=round(latency, 2),
                last_checked_at=time.time(),
            )

        # Standard non-blocking socket connect probe
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host.hostname, host.port),
                timeout=5.0,
            )
            writer.close()
            await writer.wait_closed()
            latency = (time.time() - start_t) * 1000.0
            return HostConnectionStatus(
                host_id=host.host_id,
                is_online=True,
                latency_ms=round(latency, 2),
                last_checked_at=time.time(),
            )
        except Exception as err:
            return HostConnectionStatus(
                host_id=host.host_id,
                is_online=False,
                error_message=str(err),
                last_checked_at=time.time(),
            )

    async def execute_command(
        self,
        host: SSHHostAsset,
        command: str,
        timeout_s: Optional[float] = None,
    ) -> SSHExecResult:
        """Execute a remote command via SSH on target host."""
        timeout = timeout_s or self._default_timeout_s
        start_t = time.time()

        # Handle mock driver execution
        if self._mock_driver:
            res = self._mock_driver(host, command)
            res.duration_ms = int((time.time() - start_t) * 1000)
            return res

        # Build standard SSH command
        ssh_cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            "-p", str(host.port),
        ]

        if host.key_path:
            ssh_cmd.extend(["-i", host.key_path])

        target_addr = f"{host.username}@{host.hostname}"
        ssh_cmd.extend([target_addr, command])

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                exit_code = proc.returncode if proc.returncode is not None else 1
                stdout_str = stdout_data.decode("utf-8", errors="replace")
                stderr_str = stderr_data.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                exit_code = 124
                stdout_str = ""
                stderr_str = f"Command timed out after {timeout} seconds"

            duration_ms = int((time.time() - start_t) * 1000)
            return SSHExecResult(
                host_id=host.host_id,
                command=command,
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_ms=duration_ms,
            )
        except Exception as err:
            duration_ms = int((time.time() - start_t) * 1000)
            return SSHExecResult(
                host_id=host.host_id,
                command=command,
                exit_code=255,
                stdout="",
                stderr=f"SSH connection failed: {err}",
                duration_ms=duration_ms,
            )
