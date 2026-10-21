"""Agent Asset Bridge: High-level AI Agent interface for Multi-Host SSH & SFTP operations.

Integrates TerminalLogDistiller for high-entropy output distillation and enforces
destructive command screening and human-in-the-loop (HITL) safety fences.

[INPUT]
- .models::SSHCommandResult, SSHHostAsset, SFTPFileMetadata, SFTPTransferResult
- .manager::SSHAssetManager
- .executor::SSHBridgeExecutor, SFTPBridgeEngine
- myrm_agent_harness.toolkits.code_execution.utils.log_distiller::TerminalLogDistiller

[OUTPUT]
- SSHAgentBridge: Unified high-level facade for Agent-driven remote infrastructure operations.

[POS]
Domain service in app/services/ssh_bridge/agent_bridge.py.
"""

from __future__ import annotations

import logging
from typing import Sequence

from myrm_agent_harness.toolkits.code_execution.utils.log_distiller import (
    TerminalLogDistiller,
)

from app.services.ssh_bridge.executor import SFTPBridgeEngine, SSHBridgeExecutor
from app.services.ssh_bridge.manager import SSHAssetManager
from app.services.ssh_bridge.models import (
    SFTPFileMetadata,
    SSHCommandResult,
    SSHHostAsset,
)

logger = logging.getLogger("myrm.services.ssh_bridge.agent_bridge")


class SSHAgentBridge:
    """Agent execution bridge that mediates between LLM tool-calling and remote servers."""

    def __init__(
        self,
        asset_manager: SSHAssetManager,
        executor: SSHBridgeExecutor | None = None,
        sftp_engine: SFTPBridgeEngine | None = None,
        log_distiller: TerminalLogDistiller | None = None,
    ) -> None:
        self._asset_manager = asset_manager
        self._executor = executor or SSHBridgeExecutor(asset_manager)
        self._sftp = sftp_engine or SFTPBridgeEngine(asset_manager)
        self._distiller = log_distiller or TerminalLogDistiller()

    @property
    def asset_manager(self) -> SSHAssetManager:
        return self._asset_manager

    def execute_remote(
        self,
        host_alias: str,
        command: str,
        timeout_seconds: float = 30.0,
    ) -> tuple[SSHCommandResult, str]:
        """Execute a remote command on a registered host, with high-entropy log distillation.

        Returns:
            Tuple of (SSHCommandResult, distilled_summary_text).
        """
        raw_result = self._executor.execute_command(
            host_alias=host_alias,
            command=command,
            timeout_seconds=timeout_seconds,
        )

        if raw_result.is_blocked:
            return raw_result, raw_result.stderr

        combined_output = raw_result.stdout
        if raw_result.stderr:
            combined_output += ("\n" if combined_output else "") + raw_result.stderr

        distilled = self._distiller.distill(combined_output, exit_code=raw_result.exit_code)
        distilled_text = distilled.distilled_text if distilled.distilled_text else raw_result.stdout

        return raw_result, distilled_text

    def list_remote_files(
        self,
        host_alias: str,
        remote_dir: str = "/",
    ) -> Sequence[SFTPFileMetadata]:
        """Browse remote directory listing via SFTP."""
        return self._sftp.list_directory(host_alias=host_alias, remote_dir=remote_dir)

    def get_host_summary(self, host_alias: str) -> SSHHostAsset | None:
        """Fetch host asset configuration metadata for Agent context injection."""
        return self._asset_manager.get_by_alias(host_alias)
