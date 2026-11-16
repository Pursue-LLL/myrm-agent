"""BaseAgent child-agent management.

[INPUT]
- agent.sub_agents.manager::SubagentManager, SubagentTask (POS: Subagent lifecycle manager. Manages spawn, cancel, steer (mid-course correction), state tracking, and trace_id propagation.)
- agent.sub_agents.types::SubagentConfig, SubAgentResult (POS: Subagent subsystem core type definitions. Defines all subagent-related data types, enums, and protocols.)
- agent.streaming.types::AgentEventType (POS: Streaming event types and enums — re-export from core.events.)
- utils.runtime.wakeup_registry::get_global_wakeup_handler (POS: Global registry for async wakeup events (Idle Wakeup).)
- utils.runtime.progress_sink::get_tool_progress_sink (POS: Progress event push mechanism. Tools implicitly obtain a sink via ContextVar to push intermediate progress events to the Agent SSE stream.)

[OUTPUT]
- BaseAgentChildrenMixin: BaseAgent's child-agent surface — spawn, list, cancel, steer and wait on children, and the async-wakeup notification for a result nobody has received.

[POS]
Mixin: the child-agent management methods of BaseAgent; every call delegates to the agent's SubagentManager.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from myrm_agent_harness.agent.sub_agents.manager import SubagentManager, SubagentTask
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, SubAgentResult
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = get_agent_logger(__name__)


class BaseAgentChildrenMixin:
    # Owned by ``BaseAgent.__init__``; declared here so the mixin type-checks against the same types.
    _subagent_manager: SubagentManager
    _last_context: dict[str, object]

    @property
    def _children(self) -> Mapping[str, SubagentTask]:
        return self._subagent_manager.children

    @property
    def _children_results(self) -> Mapping[str, SubAgentResult]:
        return self._subagent_manager.child_results

    async def _spawn_child(
        self,
        task_id: str,
        agent_type: str,
        task_description: str,
        config: SubagentConfig,
        context: dict[str, object],
        tool_registry_getter: Callable[[], list[BaseTool]],
        wait: bool,
        parent_type: str | None = None,
        cancel_token: CancellationToken | None = None,
        resume_command: object | None = None,
        complexity_tier: str | None = None,
    ) -> SubAgentResult | dict[str, object]:
        return await self._subagent_manager.spawn_child(
            task_id=task_id,
            agent_type=agent_type,
            task_description=task_description,
            config=config,
            context=context,
            tool_registry_getter=tool_registry_getter,
            wait=wait,
            parent_type=parent_type,
            cancel_token=cancel_token,
            resume_command=resume_command,
            complexity_tier=complexity_tier,
        )

    def list_children(self) -> list[dict[str, object]]:
        return self._subagent_manager.list_children()

    def cancel_child(self, task_id: str) -> bool:
        return self._subagent_manager.cancel_child(task_id)

    def cancel_all_children(self, include_detached: bool = True) -> int:
        return self._subagent_manager.cancel_all(include_detached=include_detached)

    def steer_child(
        self,
        task_id: str,
        message: str,
        config_overlay: dict[str, object] | None = None,
    ) -> bool:
        return self._subagent_manager.steer_child(task_id, message, config_overlay=config_overlay)

    async def wait_children(
        self,
        task_ids: list[str],
        min_success_rate: float = 0.5,
        timeout: float | None = None,
    ) -> dict[str, object]:
        return await self._subagent_manager.wait_children(task_ids, min_success_rate=min_success_rate, timeout=timeout)

    async def trigger_async_wakeup(self, result: SubAgentResult) -> None:
        """Trigger an async wakeup event for the parent agent.

        This is called by SubagentManager when a child finishes whose result nobody has received
        (started with wait=False, or a wait that gave up at its timeout while the child kept running).
        It uses the global wakeup registry to notify the Server layer (e.g. Gateway/Runner)
        to trigger a new run, while also pushing to the progress sink if active.
        """
        from myrm_agent_harness.agent.streaming.types import AgentEventType
        from myrm_agent_harness.utils.runtime.progress_sink import (
            get_tool_progress_sink,
        )
        from myrm_agent_harness.utils.runtime.wakeup_registry import (
            get_global_wakeup_handler,
        )

        session_id = None
        agent_id = "unknown"
        if self._last_context:
            session_id = self._last_context.get("session_id")
            agent_id = str(self._last_context.get("agent_id", "unknown"))

        # 1. Notify global handler (for actual background wakeup)
        handler = get_global_wakeup_handler()
        if handler:
            try:
                await handler.on_async_wakeup(result, agent_id, session_id)
                logger.info(f"Triggered global wakeup handler for subagent {result.task_id} (session_id={session_id})")
            except Exception as e:
                logger.error(f"Global wakeup handler failed: {e}")

        # 2. Push to active SSE stream (if any)
        sink = get_tool_progress_sink()
        if sink:
            try:
                await sink.emit(
                    {
                        "type": AgentEventType.ASYNC_WAKEUP.value,
                        "data": {
                            "task_id": result.task_id,
                            "agent_type": result.agent_type,
                            "success": result.success,
                            "agent_id": agent_id,
                            "session_id": session_id,
                        },
                    }
                )
            except Exception as e:
                logger.error(f"Failed to emit ASYNC_WAKEUP: {e}")
