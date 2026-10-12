"""Server service for Safe File Descriptor and Query-File IPC Pipeline.

[INPUT]
- IpcCommandDispatchRequest from app.schemas.ipc_pipeline
- SafeIpcPipeline from myrm_agent_harness.core.security.ipc

[OUTPUT]
- SafeIpcService: Subprocess dispatcher enforcing zero-CLI-argument injection
- get_safe_ipc_service: Singleton dependency provider

[POS]
Server security service. Executes background worker and subagent commands safely
without shell expansion or quote distortion.
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.core.security.ipc import (
    IpcExecutionResult,
    IpcPayloadTransport,
    SafeIpcPipeline,
    ShellArgumentInjectionError,
)

from app.schemas.ipc_pipeline import (
    IpcCommandDispatchRequest,
    IpcCommandDispatchResponse,
    IpcDispatchMode,
)

logger = logging.getLogger(__name__)


class SafeIpcService:
    """Manages shell-free IPC subprocess invocations."""

    def __init__(self, pipeline: SafeIpcPipeline | None = None) -> None:
        self._pipeline = pipeline if pipeline is not None else SafeIpcPipeline()

    @property
    def pipeline(self) -> SafeIpcPipeline:
        """Access underlying harness pipeline."""
        return self._pipeline

    async def dispatch(self, request: IpcCommandDispatchRequest) -> IpcCommandDispatchResponse:
        """Safely execute a command passing payload via query-file or stdin stream."""
        transport = (
            IpcPayloadTransport.QUERY_FILE
            if request.transport == IpcDispatchMode.QUERY_FILE
            else IpcPayloadTransport.STDIN_STREAM
        )

        try:
            self._pipeline.validate_command_safety(request.command)
        except (ShellArgumentInjectionError, ValueError) as exc:
            logger.warning("Rejected unsafe command execution: %s", exc)
            return IpcCommandDispatchResponse(
                returncode=-1,
                stdout="",
                stderr=f"Command validation rejected: {exc}",
                duration_seconds=0.0,
                status="rejected",
            )

        start_time = time.monotonic()
        result: IpcExecutionResult = await self._pipeline.dispatch(
            cmd_args=request.command,
            payload=request.payload,
            transport=transport,
            timeout_seconds=request.timeout_seconds,
        )
        duration = time.monotonic() - start_time

        status_str = "success" if result.returncode == 0 else ("timeout" if result.returncode == -1 and "timed out" in result.stderr else "error")

        return IpcCommandDispatchResponse(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=round(duration, 4),
            status=status_str,
        )


_global_safe_ipc_service: SafeIpcService | None = None


def get_safe_ipc_service() -> SafeIpcService:
    """Singleton getter for SafeIpcService."""
    global _global_safe_ipc_service
    if _global_safe_ipc_service is None:
        _global_safe_ipc_service = SafeIpcService()
    return _global_safe_ipc_service
