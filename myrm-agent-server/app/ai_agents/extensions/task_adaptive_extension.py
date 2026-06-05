from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.extensions.protocols import AgentExtension

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class TaskAdaptiveExtension(AgentExtension):
    """Extension that dynamically injects task-adaptive JIT guidance middleware."""

    def __init__(self, task_adaptive_digest: dict[str, object] | None) -> None:
        self._middlewares: list[AgentMiddleware[object, object]] = []

        if not task_adaptive_digest:
            return

        try:
            from myrm_agent_harness.agent.event_log.types import AntiPattern, FileHotspot, TraceRunDigest
            from myrm_agent_harness.agent.middlewares.task_adaptive_middleware import TaskAdaptiveMiddleware

            digest_data = task_adaptive_digest.copy()
            hotspots_raw = digest_data.get("hotspots")
            if isinstance(hotspots_raw, list):
                digest_data["hotspots"] = [FileHotspot(**h) if isinstance(h, dict) else h for h in hotspots_raw]
            anti_raw = digest_data.get("anti_patterns")
            if isinstance(anti_raw, list):
                digest_data["anti_patterns"] = [AntiPattern(**a) if isinstance(a, dict) else a for a in anti_raw]

            digest = TraceRunDigest(**digest_data)
            self._middlewares.append(TaskAdaptiveMiddleware(trace_digest=digest))
            logger.info("TaskAdaptiveExtension: prepared JIT middleware from digest")
        except Exception as e:
            logger.warning("TaskAdaptiveExtension: failed to build middleware: %s", e)

    @property
    def name(self) -> str:
        return "TaskAdaptiveExtension"

    async def on_agent_init(self, agent: BaseAgent) -> None:
        pass

    async def on_agent_shutdown(self, agent: BaseAgent) -> None:
        pass

    def get_tools(self) -> list[BaseTool] | None:
        return None

    def get_middlewares(self) -> list[AgentMiddleware[object, object]] | None:
        return self._middlewares or None
