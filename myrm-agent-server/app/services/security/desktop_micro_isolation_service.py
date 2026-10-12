"""Desktop Host Auth & Tool Routing Micro-Isolation Service.

[INPUT]
- SanitizeEnvironmentRequest, RouteToolExecutionRequest.

[OUTPUT]
- SanitizeEnvironmentResponse, RouteToolExecutionResponse, IsolationStatusDisclosureDto.

[POS]
- Server security service. Wraps harness DesktopToolRoutingDispatcher to enforce
  Gondolin-pattern host credential stripping, workspace write-through boundary validation,
  and fail-closed tool isolation.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from myrm_agent_harness.core.security.desktop_micro_isolation import (
    DesktopMicroIsolationError,
    DesktopToolRoutingDispatcher,
    ForbiddenWorkspaceAccessError,
    HostCredentialPolicy,
    IsolationLevel,
    MicroIsolationUnavailableError,
    RoutingDestination,
    WorkspaceMountPolicy,
)

from app.schemas.desktop_micro_isolation import (
    IsolationStatusDisclosureDto,
    RouteToolExecutionRequest,
    RouteToolExecutionResponse,
    SanitizeEnvironmentRequest,
    SanitizeEnvironmentResponse,
)

logger = logging.getLogger(__name__)


class DesktopMicroIsolationService:
    """Service governing desktop host credential isolation and tool routing dispatch."""

    def __init__(
        self,
        workspace_root: str | None = None,
        provider_available: bool = True,
    ) -> None:
        self._workspace_root = workspace_root or os.getcwd()
        self._provider_available = provider_available
        self._workspace_policy = WorkspaceMountPolicy(workspace_root=self._workspace_root)
        self._credential_policy = HostCredentialPolicy()
        self._dispatcher = DesktopToolRoutingDispatcher(
            workspace_policy=self._workspace_policy,
            credential_policy=self._credential_policy,
            provider_available=self._provider_available,
        )

    def set_workspace_root(self, workspace_root: str) -> None:
        """Update workspace root path for isolation mounting."""
        self._workspace_root = workspace_root
        self._workspace_policy = WorkspaceMountPolicy(workspace_root=self._workspace_root)
        self._rebuild_dispatcher()

    def set_provider_availability(self, available: bool) -> None:
        """Toggle micro-isolation provider availability."""
        self._provider_available = available
        self._rebuild_dispatcher()

    def _rebuild_dispatcher(self) -> None:
        """Reconstruct dispatcher with updated policies."""
        self._dispatcher = DesktopToolRoutingDispatcher(
            workspace_policy=self._workspace_policy,
            credential_policy=self._credential_policy,
            provider_available=self._provider_available,
        )

    def sanitize_env(
        self, req: SanitizeEnvironmentRequest
    ) -> SanitizeEnvironmentResponse:
        """Purge host secrets from environment dictionary."""
        clean_env, stripped_keys = self._dispatcher.sanitize_environment(req.host_env)
        return SanitizeEnvironmentResponse(
            clean_env=clean_env,
            stripped_keys=list(stripped_keys),
        )

    def route_tool_execution(
        self,
        req: RouteToolExecutionRequest,
        executor_fn: Callable[[dict[str, str]], str] | None = None,
    ) -> RouteToolExecutionResponse:
        """Route tool invocation into micro-isolation or host process according to safety policies."""
        # Create default execution simulation if none provided
        action = executor_fn or (
            lambda env: f"Executed '{req.tool_name}' successfully with sanitized environment of {len(env)} keys"
        )

        try:
            # Update credential policy override if requested
            if req.allow_unisolated_override != self._credential_policy.allow_unisolated_override:
                temp_cred_policy = HostCredentialPolicy(
                    allow_unisolated_override=req.allow_unisolated_override
                )
                temp_dispatcher = DesktopToolRoutingDispatcher(
                    workspace_policy=self._workspace_policy,
                    credential_policy=temp_cred_policy,
                    provider_available=self._provider_available,
                )
                result = temp_dispatcher.dispatch_and_execute(
                    tool_name=req.tool_name,
                    action_fn=action,
                    host_env=req.host_env,
                    target_path=req.target_path,
                )
            else:
                result = self._dispatcher.dispatch_and_execute(
                    tool_name=req.tool_name,
                    action_fn=action,
                    host_env=req.host_env,
                    target_path=req.target_path,
                )

            return RouteToolExecutionResponse(
                tool_name=result.tool_name,
                destination=result.destination.value,
                isolation_level=result.isolation_level.value,
                workspace_root=result.workspace_root,
                output=result.output,
                stripped_credential_keys=list(result.stripped_credential_keys),
                is_blocked=False,
                error_message=None,
            )

        except (MicroIsolationUnavailableError, ForbiddenWorkspaceAccessError, DesktopMicroIsolationError) as exc:
            logger.warning("Tool routing blocked by micro-isolation policy: %s", exc)
            dest = (
                RoutingDestination.MICRO_ISOLATION_SANDBOX.value
                if self._dispatcher.is_dangerous_tool(req.tool_name)
                else RoutingDestination.HOST_PROCESS.value
            )
            return RouteToolExecutionResponse(
                tool_name=req.tool_name,
                destination=dest,
                isolation_level=IsolationLevel.FAIL_CLOSED_BLOCKED.value,
                workspace_root=self._workspace_root,
                output="",
                stripped_credential_keys=[],
                is_blocked=True,
                error_message=str(exc),
            )

    def get_isolation_status(self) -> IsolationStatusDisclosureDto:
        """Produce system-level disclosure of active tool micro-isolation capabilities."""
        level = (
            IsolationLevel.MICRO_SANDBOX.value
            if self._provider_available
            else IsolationLevel.FAIL_CLOSED_BLOCKED.value
        )
        notice = (
            "Micro-isolation sandbox is active. Dangerous tools (bash, file_write) run in micro-VM "
            "with purged host credentials and strict workspace confinement."
            if self._provider_available
            else "Micro-isolation provider unavailable. Fail-closed contract enforced; dangerous tools "
            "will be strictly blocked unless explicit unisolated override is authorized."
        )
        return IsolationStatusDisclosureDto(
            provider_available=self._provider_available,
            default_isolation_level=level,
            workspace_root=self._workspace_root,
            fail_closed_enforced=True,
            disclosure_notice=notice,
        )


_service_instance: DesktopMicroIsolationService | None = None


def get_desktop_micro_isolation_service() -> DesktopMicroIsolationService:
    """Obtain or initialize the singleton DesktopMicroIsolationService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DesktopMicroIsolationService()
    return _service_instance
