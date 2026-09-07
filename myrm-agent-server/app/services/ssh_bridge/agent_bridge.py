"""Agent Execution Bridge for Remote SSH and SFTP Operations.

Integrates HostAssetVault, SSHConnectionPool, SFTPManager, and TerminalLogDistiller
to provide safety-gated, distilled remote execution tools for AI agents.

[INPUT]
- .models::SSHHostAsset, SSHExecResult, SFTPItemInfo
- .vault::SSHHostVault
- .pool::SSHConnectionPool
- .sftp_manager::SFTPManager
- myrm_agent_harness.toolkits.code_execution.utils.log_distiller::TerminalLogDistiller
- re, typing, logging

[OUTPUT]
- SSHAgentBridge: Dispatches guarded remote commands and SFTP queries for agents.

[POS]
Domain service in app/services/ssh_bridge/agent_bridge.py.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from myrm_agent_harness.toolkits.code_execution.utils.log_distiller import (
    TerminalLogDistiller,
)

from .models import SFTPItemInfo, SSHExecResult, SSHHostAsset
from .pool import SSHConnectionPool
from .sftp_manager import SFTPManager
from .vault import SSHHostVault

logger = logging.getLogger("myrm.services.ssh_bridge.agent_bridge")

# High-risk command patterns requiring explicit user approval unless host is pre-trusted
_DESTRUCTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+-(?:r|f|rf|fr)\s+(?:/|\*|~|/\w+)", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r">\s*/dev/sd[a-z]", re.IGNORECASE),
    re.compile(r"\b(?:reboot|shutdown|init\s+0|poweroff)\b", re.IGNORECASE),
    re.compile(r"\bchmod\s+-R\s+777\s+/", re.IGNORECASE),
)


class SSHAgentBridge:
    """Agent-facing gateway for multi-host remote command execution and SFTP queries."""

    def __init__(
        self,
        vault: SSHHostVault,
        pool: SSHConnectionPool,
        sftp: SFTPManager,
        distiller: Optional[TerminalLogDistiller] = None,
    ) -> None:
        self._vault = vault
        self._pool = pool
        self._sftp = sftp
        self._distiller = distiller or TerminalLogDistiller()

    def check_command_safety(self, host: SSHHostAsset, command: str) -> Tuple[bool, Optional[str]]:
        """Validate whether command is safe to execute automatically."""
        if host.is_trusted:
            return True, None

        for pattern in _DESTRUCTIVE_PATTERNS:
            if pattern.search(command):
                return False, f"Destructive command detected matching safety gate: {pattern.pattern}"

        return True, None

    async def execute_remote_tool(
        self,
        host_query: str,
        command: str,
        timeout_s: Optional[float] = None,
    ) -> SSHExecResult:
        """Execute command on resolved remote host with log distillation."""
        host = self._vault.find_by_alias_or_hostname(host_query)
        if not host:
            return SSHExecResult(
                host_id="unknown",
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"Host '{host_query}' not found in SSH Host Vault.",
            )

        is_safe, reason = self.check_command_safety(host, command)
        if not is_safe:
            return SSHExecResult(
                host_id=host.host_id,
                command=command,
                exit_code=126,
                stdout="",
                stderr=f"Execution blocked by safety policy: {reason}. User approval required.",
            )

        # Run command via connection pool
        raw_result = await self._pool.execute_command(host, command, timeout_s=timeout_s)

        # Distill raw log output to prevent context window blowup
        combined_logs = f"{raw_result.stdout}\n{raw_result.stderr}".strip()
        distilled = self._distiller.distill(
            raw_text=combined_logs,
            exit_code=raw_result.exit_code,
        )

        raw_result.distilled_summary = distilled.distilled_text
        return raw_result

    async def list_remote_files_tool(
        self,
        host_query: str,
        remote_path: str = ".",
    ) -> Dict[str, Any]:
        """List files in remote path for agent context."""
        host = self._vault.find_by_alias_or_hostname(host_query)
        if not host:
            return {"error": f"Host '{host_query}' not found in SSH Host Vault.", "items": []}

        items: List[SFTPItemInfo] = await self._sftp.list_directory(host, remote_path)
        return {
            "host_id": host.host_id,
            "alias": host.alias,
            "path": remote_path,
            "items": [item.model_dump() for item in items],
            "total_count": len(items),
        }

    async def read_remote_file_tool(
        self,
        host_query: str,
        remote_path: str,
        max_lines: int = 100,
    ) -> str:
        """Read trailing lines from remote file."""
        host = self._vault.find_by_alias_or_hostname(host_query)
        if not host:
            return f"Error: Host '{host_query}' not found in SSH Host Vault."

        return await self._sftp.read_remote_file_tail(host, remote_path, lines=max_lines)
