"""Service for managing SSH configurations, host lookup, health probing, and safe execution.

Parses standard ~/.ssh/config, caches host assets, provides network reachability probing,
and handles parameterized, safe subprocess remote execution with timeout and safety guards.

[INPUT]
- .models::SSHAssetSummary, SSHHostConfig, SSHProbeResult, SSHCommandResult, SFTPTransferResult
- pathlib::Path
- asyncio, logging, os, re, socket, time
- typing::Dict, List, Optional

[OUTPUT]
- SSHAssetService: Core coordinator for SSH asset inventory, probing, and execution.
- get_ssh_asset_service: Singleton provider.

[POS]
Domain service in app/services/ssh_vault/.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import time
from pathlib import Path
from typing import Dict, List, Optional

from app.services.ssh_vault.models import (
    SFTPTransferResult,
    SSHAssetSummary,
    SSHCommandResult,
    SSHHostConfig,
    SSHProbeResult,
)

logger = logging.getLogger("myrm.services.ssh_vault")

# Strict pattern guard for destructive commands without explicit confirmation
_HIGH_RISK_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-[rR]f\s+/\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if=.*of=/dev/"),
    re.compile(r":\(\)\{\s*:\s*\|\s*:\s*&\s*\};\s*:"),  # Fork bomb
    re.compile(r">\s*/dev/sd[a-z]"),
]


class SSHAssetService:
    """Enterprise SSH & SFTP asset coordinator for discovery, probing, and execution."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._config_path = config_path or Path.home() / ".ssh" / "config"
        self._hosts_cache: Dict[str, SSHHostConfig] = {}
        self._last_loaded: float = 0.0

    def register_host(self, host: SSHHostConfig) -> bool:
        """Register or update a host asset with strict validation."""
        if not host.validate_alias():
            raise ValueError(f"Invalid host alias: {host.host_alias}. Only alphanumeric, '.', '-' and '_' allowed.")
        self._hosts_cache[host.host_alias] = host
        logger.info("Registered SSH host asset '%s' (%s:%d)", host.host_alias, host.hostname, host.port)
        return True

    def parse_ssh_config(self, text_content: Optional[str] = None) -> List[SSHHostConfig]:
        """Parse SSH configuration format into structured SSHHostConfig items."""
        if text_content is None:
            if not self._config_path.exists():
                return list(self._hosts_cache.values())
            try:
                text_content = self._config_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to read SSH config from %s: %s", self._config_path, e)
                return list(self._hosts_cache.values())

        hosts: List[SSHHostConfig] = []
        current_host: Optional[str] = None
        current_data: Dict[str, str] = {}

        def flush_current() -> None:
            if current_host and current_host != "*" and not current_host.startswith("*"):
                hostname = current_data.get("hostname", current_host)
                port_str = current_data.get("port", "22")
                try:
                    port = int(port_str)
                except ValueError:
                    port = 22
                user = current_data.get("user", "root")
                identity = current_data.get("identityfile")
                if identity:
                    identity = str(Path(identity).expanduser())

                hosts.append(
                    SSHHostConfig(
                        host_alias=current_host,
                        hostname=hostname,
                        port=port,
                        user=user,
                        identity_file=identity,
                        tags=["ssh-config"],
                    )
                )

        for line in text_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) < 2:
                continue

            key, value = parts[0].lower(), parts[1].strip().strip('"').strip("'")

            if key == "host":
                flush_current()
                current_host = value.split()[0]
                current_data = {}
            elif current_host is not None:
                current_data[key] = value

        flush_current()
        for h in hosts:
            self._hosts_cache[h.host_alias] = h
        self._last_loaded = time.time()
        return list(self._hosts_cache.values())

    def get_host(self, host_alias: str) -> Optional[SSHHostConfig]:
        """Look up host configuration by alias."""
        if not self._hosts_cache or (time.time() - self._last_loaded > 60):
            self.parse_ssh_config()
        return self._hosts_cache.get(host_alias)

    def list_hosts(self) -> List[SSHHostConfig]:
        """List all discovered and registered host configurations."""
        return self.parse_ssh_config()

    def get_summary(self) -> SSHAssetSummary:
        """Get summary of all registered and parsed SSH hosts."""
        if not self._hosts_cache or (time.time() - self._last_loaded > 60):
            hosts = self.parse_ssh_config()
        else:
            hosts = list(self._hosts_cache.values())
        return SSHAssetSummary(
            total_hosts=len(hosts),
            hosts=hosts,
            config_source=str(self._config_path),
        )

    def is_high_risk_command(self, command: str) -> bool:
        """Check if command matches destructive or system wipe patterns."""
        cmd_clean = command.strip()
        for pattern in _HIGH_RISK_COMMAND_PATTERNS:
            if pattern.search(cmd_clean):
                return True
        return False

    async def probe_host(self, host_alias: str, timeout_seconds: float = 3.0) -> SSHProbeResult:
        """Probe network reachability for target host alias."""
        host = self.get_host(host_alias)
        if not host:
            return SSHProbeResult(
                host_alias=host_alias,
                is_reachable=False,
                error_message=f"Host alias '{host_alias}' not found in SSH configuration",
            )

        start_time = time.perf_counter()
        loop = asyncio.get_running_loop()

        def _check_tcp() -> bool:
            try:
                with socket.create_connection((host.hostname, host.port), timeout=timeout_seconds):
                    return True
            except Exception:
                return False

        try:
            is_ok = await asyncio.wait_for(loop.run_in_executor(None, _check_tcp), timeout=timeout_seconds + 1.0)
            latency = (time.perf_counter() - start_time) * 1000.0
            return SSHProbeResult(
                host_alias=host_alias,
                is_reachable=is_ok,
                latency_ms=round(latency, 2) if is_ok else None,
                error_message=None if is_ok else f"Connection timed out to {host.hostname}:{host.port}",
            )
        except Exception as e:
            return SSHProbeResult(
                host_alias=host_alias,
                is_reachable=False,
                error_message=str(e),
            )

    async def execute_remote_command(
        self,
        host_alias: str,
        command: str,
        *,
        timeout_seconds: float = 30.0,
        allow_high_risk: bool = False,
    ) -> SSHCommandResult:
        """Execute a remote shell command on the target host via safe SSH subprocess."""
        host = self.get_host(host_alias)
        if not host:
            return SSHCommandResult(
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
            return SSHCommandResult(
                host_alias=host_alias,
                command=command,
                exit_code=126,
                stdout="",
                stderr="Execution blocked by safety policy: high-risk destructive command detected.",
                duration_ms=0,
                is_blocked_high_risk=True,
                error_message="High-risk command blocked by security guard.",
            )

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

            return SSHCommandResult(
                host_alias=host_alias,
                command=command,
                exit_code=exit_code,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning("Remote command timed out on host '%s' after %.1fs", host_alias, timeout_seconds)
            return SSHCommandResult(
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
            return SSHCommandResult(
                host_alias=host_alias,
                command=command,
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                error_message=str(e),
            )


_GLOBAL_SSH_ASSET_SERVICE = SSHAssetService()


def get_ssh_asset_service() -> SSHAssetService:
    """Retrieve singleton instance of SSHAssetService."""
    return _GLOBAL_SSH_ASSET_SERVICE
