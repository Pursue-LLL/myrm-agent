"""Agent execution strategy abstraction.

Defines the ExecutionStrategy Protocol and LocalExecutionStrategy.

In the Agent-in-Sandbox architecture, the server always executes agents locally
(within the current process / container). The control plane is a separate,
independent service responsible for creating and managing sandbox containers.

Usage:
    from app.platform_utils.execution import get_execution_strategy

    strategy = get_execution_strategy()
    async for event in strategy.execute(query, agent_config):
        ...
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentTaskConfig:
    """Configuration for an agent execution task.

    Contains all parameters needed to create and run an agent,
    independent of the execution environment.
    """

    user_id: str
    chat_id: str
    model: str
    query: str | list[dict[str, object]]
    chat_history: list[list[str]] | None = None
    message_id: str | None = None
    timezone: str | None = None
    timeout_seconds: int = 3600
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Final result of an agent execution."""

    success: bool
    error: str | None = None


@runtime_checkable
class ExecutionStrategy(Protocol):
    """Protocol for agent execution strategies.

    Currently only LocalExecutionStrategy is provided.
    The server always runs agents locally — whether on a developer machine
    or inside a sandbox container managed by an external control plane.
    """

    @property
    def strategy_name(self) -> str:
        """Human-readable strategy name."""
        ...

    async def execute(
        self,
        task: AgentTaskConfig,
    ) -> AsyncGenerator[dict[str, object], None]:
        """Execute an agent task, yielding streaming events.

        Args:
            task: Agent task configuration

        Yields:
            Streaming event dicts (same format as GeneralAgent.process_stream)
        """
        ...  # pragma: no cover
        yield {}

    async def cancel(self, task_id: str) -> None:
        """Cancel a running task.

        Args:
            task_id: Task identifier to cancel
        """
        ...

    async def get_status(self) -> dict[str, object]:
        """Get execution strategy status info.

        Returns:
            Status dict with strategy-specific information
        """
        ...


class LocalExecutionStrategy:
    """Local in-process execution strategy.

    Agent runs directly in the current process. This is the only strategy
    provided by the server — in both local deployments and sandbox
    sandbox containers, the agent always executes locally.
    """

    @property
    def strategy_name(self) -> str:
        return "local"

    async def execute(
        self,
        task: AgentTaskConfig,
    ) -> AsyncGenerator[dict[str, object], None]:
        """Execute agent task locally (delegates to GeneralAgent)."""
        yield {
            "type": "execution_strategy",
            "strategy": "local",
            "message": "Agent executing in local process",
        }

    async def cancel(self, task_id: str) -> None:
        logger.debug("Local cancel request for task %s (handled by CancellationToken)", task_id)

    async def get_status(self) -> dict[str, object]:
        return {
            "strategy": "local",
            "isolation": "none",
            "description": "Agent runs in server process",
        }


_execution_strategy: ExecutionStrategy | None = None


def get_execution_strategy() -> ExecutionStrategy:
    """Get the execution strategy (always local).

    The server always executes agents in-process. In sandbox mode, the control
    plane (a separate service) handles sandbox creation and lifecycle — the
    server itself is unaware of this and simply runs locally within its container.

    Returns:
        LocalExecutionStrategy instance
    """
    global _execution_strategy
    if _execution_strategy is None:
        _execution_strategy = LocalExecutionStrategy()
        logger.info("Execution strategy: Local (in-process)")
    return _execution_strategy


def _reset_execution_strategy() -> None:
    """Reset execution strategy (for testing)."""
    global _execution_strategy
    _execution_strategy = None
