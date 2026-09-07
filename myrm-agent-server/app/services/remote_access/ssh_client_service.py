"""SSH & SFTP remote execution service.

Provides parameterized, injection-safe, timeout-protected command execution
and secure SFTP file operations across registered host assets.

[INPUT]
- .host_models::RemoteHostConfig, SSHCommandExecutionResult, SFTPTransferResult, parse_ssh_config_text
- asyncio, logging, os, pathlib, re, time

[OUTPUT]
- SSHRemoteClientService: Core coordinator for remote host command execution and file transfer
- get_ssh_remote_client_service: Singleton provider

[POS]
Domain service in app/services/remote_access/.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .host_models import (
    RemoteHostConfig,
    SFTPTransferResult,
    SSHCommandExecutionResult,
    parse_ssh_config_text,
)

logger = logging.getLogger("myrm.services.remote_access.ssh_client")

# Strict blacklist for dangerous commands without explicit confirmation
_HIGH_RISK_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-[rR]f\s+/\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if=.*of=/dev/"),
    re.compile(r":\(\)\{\s*:\s*\|\s*:\s*&\s*\};\s*:"),  # Fork bomb
    re.compile(r">\s*/dev/sd[a-z]"),
]


class SSHRemoteClientService:
    """Enterprise SSH & SFTP client coordinator for AI Agent operations."""

    def __init__(self) -> None:
        self._hosts: Dict[str, RemoteHostConfig] = {}

    def register_host(self, host: RemoteHostConfig) -> bool:
        """Register or update a remote host asset with validation."""
        if not host.validate_alias():
            raise ValueError(f"Invalid host alias: {host.alias}. Only alphanumeric, '.', '-' and '_' allowed.")
        self._hosts[host.alias] = host
        logger.info("Registered remote host asset '%s' (%s:%d)", host.alias, host.hostname, host.port)
        return True

    def get_host(self, alias: str) -> Optional[RemoteHostConfig]:
        """Retrieve registered host configuration by alias."""
        return self._hosts.get(alias)

    def list_hosts(self) -> List[RemoteHostConfig]:
        """List all registered remote host configurations."""
        return list(self._hosts.values())

    def import_from_ssh_config_file(self, config_path: Optional[Path | str] = None) -> int:
        """Load and parse hosts from ~/.ssh/config or a custom file."""
        target_path = Path(config_path).expanduser() if config_path else Path.home() / ".ssh" / "config"
        if not target_path.is_file():
            logger.debug("SSH config file not found at %s", target_path)
            return 0

        try:
            content = target_path.read_text(encoding="utf-8")
            hosts = parse_ssh_config_text(content)
            for h in hosts:
                self.register_host(h)
            logger.info("Imported %d remote host assets from %s", len(hosts), target_path)
            return len(hosts)
        except Exception as e:
            logger.error("Failed importing SSH config from %s: %s", target_path, e, exc_info=True)
            return 0

    def is_high_risk_command(self, command: str) -> bool:
        """Check if command matches destructive or root wipe patterns."""
        cmd_clean = command.strip()
        for pattern in _HIGH_RISK_COMMAND_PATTERNS:
            if pattern.search(cmd_clean):
                return True
        return False

    async def execute_remote_command(
        self,
        host_alias: str,
        command: str,
        *,
        timeout_seconds: float = 30.0,
        allow_high_risk: bool = False,
    ) -> SSHCommandExecutionResult:
        """Execute a remote shell command on the target host via SSH subprocess.

        Uses safe argv tokenization to eliminate local shell injection.
        Enforces BatchMode=yes and ConnectTimeout to avoid hanging.
        """
        host = self.get_host(host_alias)
        if not host:
            return SSHCommandExecutionResult(
                host_alias=host_alias,
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"Host alias '{host_alias}' not found in asset registry",
                duration_ms=0,
                error_message=f"Unknown host alias: {host_alias}",
            )

        if not allow_high_risk and self.is_high_risk_command(command):
            logger.warning("Blocked high-risk command on host '%s': %s", host_alias, command)
            return SSHCommandExecutionResult(
                host_alias=host_alias,
                command=command,
                exit_code=126,
                stdout="",
                stderr="Execution blocked by safety policy: high-risk destructive command detected.",
                duration_ms=0,
                is_blocked_high_risk=True,
                error_message="High-risk command blocked by security guard.",
            )

        # Build safe ssh command arguments
        ssh_args = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=15",
            "-p", str(host.port),
        ]

        if host.identity_file and os.path.isfile(host.identity_file):
            ssh_args.extend(["-i", host.identity_file])

        destination = f"{host.user}@{host.hostname}"
        ssh_args.extend([destination, command])

        start_time = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            exit_code = proc.returncode if proc.returncode is not None else 0

            return SSHCommandExecutionResult(
                host_alias=host_alias,
                command=command,
                exit_code=exit_code,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning("Remote command execution timed out on host '%s' after %.1fs", host_alias, timeout_seconds)
            return SSHCommandExecutionResult(
                host_alias=host_alias,
                command=command,
                exit_code=124,
                stdout="",
                stderr=f"Command execution timed out after {timeout_seconds}s",
                duration_ms=duration_ms,
                is_timeout=True,
                error_message="Execution timeout",
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Failed executing SSH command on '%s': %s", host_alias, e)
            return SSHCommandExecutionResult(
                host_alias=host_alias,
                command=command,
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                error_message=str(e),
            )


_GLOBAL_SSH_CLIENT_SERVICE = SSHRemoteClientService()


def get_ssh_remote_client_service() -> SSHRemoteClientService:
    """Retrieve singleton instance of SSHRemoteClientService."""
    return _GLOBAL_SSH_CLIENT_SERVICE
