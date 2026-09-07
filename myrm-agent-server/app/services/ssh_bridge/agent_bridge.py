"""AI Agent SSH & SFTP Execution Bridge with high-entropy log distillation and security guard.

[INPUT]
- .models::SSHHostAsset, SSHExecResult, SFTPItemInfo
- .vault::SSHHostVault
- .pool::SSHConnectionPool
- .sftp_manager::SFTPManager
- myrm_agent_harness.toolkits.code_execution.utils.log_distiller::TerminalLogDistiller
- re, logging

[OUTPUT]
- SSHAgentBridge: Single entry point for AI Agent to discover and invoke remote host operations.

[POS]
Domain service in app/services/ssh_bridge/agent_bridge.py.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from myrm_agent_harness.toolkits.code_execution.utils.log_distiller import (
    TerminalLogDistiller,
)

from .models import SFTPItemInfo, SSHExecResult, SSHHostAsset
from .pool import SSHConnectionPool
from .sftp_manager import SFTPManager
from .vault import SSHHostVault

logger = logging.getLogger("myrm.services.ssh_bridge.agent_bridge")

# High-risk destructive commands requiring mandatory human review
DANGEROUS_PATTERNS = [
    r"\brm\s+-[rfRF]+\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+-R\s+777\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\biptables\s+-F\b",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
]


class SSHAgentBridge:
    """Provides high-level, audited remote SSH operations for AI Agent with log distillation."""

    def __init__(
        self,
        vault: SSHHostVault,
        pool: SSHConnectionPool,
        sftp: SFTPManager,
    ) -> None:
        self._vault = vault
        self._pool = pool
        self._sftp = sftp
        self._distiller = TerminalLogDistiller()

    def check_command_safety(self, command: str) -> Tuple[bool, Optional[str]]:
        """Validate whether command contains high-risk destructive patterns."""
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return False, f"Blocked dangerous command pattern: {pattern}"
        return True, None

    async def execute_remote(
        self,
        host_query: str,
        command: str,
        allow_destructive: bool = False,
    ) -> SSHExecResult:
        """Resolve host asset, audit command safety, execute, and distill terminal logs."""
        host = self._vault.find_by_alias_or_hostname(host_query)
        if not host:
            return SSHExecResult(
                host_id=host_query,
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"Host '{host_query}' not found in SSH asset vault. Please check available hosts.",
            )

        # Safety Guard
        is_safe, reason = self.check_command_safety(command)
        if not is_safe and not (allow_destructive and host.is_trusted):
            return SSHExecResult(
                host_id=host.host_id,
                command=command,
                exit_code=126,
                stdout="",
                stderr=f"Security Gate Intercept: {reason}. Destructive actions require manual approval.",
            )

        # Execute
        result = await self._pool.execute_command(host, command)

        # High-entropy Log Distillation to save prompt tokens
        raw_combined = f"{result.stdout}\n{result.stderr}".strip()
        if raw_combined:
            distilled = self._distiller.distill(raw_combined)
            result.distilled_summary = distilled

        return result

    async def list_remote_files(
        self,
        host_query: str,
        path: str = ".",
    ) -> Tuple[Optional[List[SFTPItemInfo]], str]:
        """List files on remote host via SFTP manager."""
        host = self._vault.find_by_alias_or_hostname(host_query)
        if not host:
            return None, f"Host '{host_query}' not found in SSH vault."
        items = await self._sftp.list_directory(host, path)
        return items, "OK"
