"""Service for managing SSH configurations, host lookup, and health probing.

Parses standard ~/.ssh/config and provides secure host resolution.

[INPUT]
- .models::SSHHostConfig, SSHProbeResult, SSHAssetSummary
- pathlib::Path
- asyncio, re, time, socket, logging

[OUTPUT]
- SSHAssetService: Core service for host inventory and status probing.

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
    SSHAssetSummary,
    SSHHostConfig,
    SSHProbeResult,
)

logger = logging.getLogger("myrm.services.ssh_vault")


class SSHAssetService:
    """Service to discover, resolve, and probe SSH hosts."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._config_path = config_path or Path.home() / ".ssh" / "config"
        self._hosts_cache: Dict[str, SSHHostConfig] = {}
        self._last_loaded: float = 0.0

    def parse_ssh_config(self, text_content: Optional[str] = None) -> List[SSHHostConfig]:
        """Parse SSH configuration format into structured SSHHostConfig items."""
        if text_content is None:
            if not self._config_path.exists():
                return []
            try:
                text_content = self._config_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to read SSH config from %s: %s", self._config_path, e)
                return []

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
                    identity = os.path.expanduser(identity)

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

            key, value = parts[0].lower(), parts[1].strip()

            if key == "host":
                flush_current()
                current_host = value.split()[0]
                current_data = {}
            elif current_host is not None:
                current_data[key] = value

        flush_current()
        self._hosts_cache = {h.host_alias: h for h in hosts}
        self._last_loaded = time.time()
        return hosts

    def get_host(self, host_alias: str) -> Optional[SSHHostConfig]:
        """Look up host configuration by alias."""
        if not self._hosts_cache or (time.time() - self._last_loaded > 60):
            self.parse_ssh_config()
        return self._hosts_cache.get(host_alias)

    def get_summary(self) -> SSHAssetSummary:
        """Get summary of all registered and parsed SSH hosts."""
        hosts = self.parse_ssh_config()
        return SSHAssetSummary(
            total_hosts=len(hosts),
            hosts=hosts,
            config_source=str(self._config_path),
        )

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
