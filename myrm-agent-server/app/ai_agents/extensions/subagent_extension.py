from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.extensions.protocols import AgentExtension

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SubagentManagementExtension(AgentExtension):
    """Extension that injects subagent management tools into the agent.

    Tools are created in ``on_agent_init`` (they require a live ``BaseAgent`` reference)
    and injected via ``agent.add_tools()``, which triggers an agent graph rebuild.
    ``get_tools()`` always returns ``None`` because tools cannot be provided statically.
    """

    def __init__(
        self,
        jit_subagents: dict[str, object],
        subagent_ids: list[str],
    ) -> None:
        self.jit_subagents = jit_subagents
        self.subagent_ids = subagent_ids

    @property
    def name(self) -> str:
        return "SubagentManagementExtension"

    async def on_agent_init(self, agent: BaseAgent) -> None:
        from myrm_agent_harness.agent.meta_tools.spawn_subagent import (
            create_batch_delegate_tasks_tool,
            create_cancel_subagent_tool,
            create_delegate_parallel_tasks_tool,
            create_delegate_task_tool,
            create_list_subagents_tool,
            create_steer_subagent_tool,
            update_delegate_task_description,
        )

        from app.ai_agents.general_agent.blueprint_materializer import (
            materialize_jit_configs,
        )
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        def _tool_registry_getter() -> list[object]:
            return list(agent._cached_tools or agent.user_tools) if agent else []

        jit_configs = materialize_jit_configs(self.jit_subagents)
        combined_ids = list(self.subagent_ids)
        if jit_configs:
            combined_ids = list(set(combined_ids + list(jit_configs.keys())))

        catalog = DatabaseSubagentCatalog(
            bound_agent_ids=combined_ids,
            jit_configs=jit_configs,
        )
        delegate_tool = create_delegate_task_tool(
            agent,
            tool_registry_getter=_tool_registry_getter,
            catalog=catalog,
        )
        await update_delegate_task_description(delegate_tool, catalog)

        subagent_tools = [
            delegate_tool,
            create_batch_delegate_tasks_tool(
                agent,
                tool_registry_getter=_tool_registry_getter,
                catalog=catalog,
                delegate_tool=delegate_tool,
            ),
            create_delegate_parallel_tasks_tool(
                agent,
                tool_registry_getter=_tool_registry_getter,
                catalog=catalog,
            ),
            create_list_subagents_tool(agent),
            create_cancel_subagent_tool(agent),
            create_steer_subagent_tool(agent),
        ]
        agent.add_tools(subagent_tools)
        logger.info("Subagent tools loaded via Extension: delegate/batch/parallel/list/cancel/steer")

    async def on_agent_shutdown(self, agent: BaseAgent) -> None:
        pass

    def get_tools(self) -> list[BaseTool] | None:
        return None

    def get_middlewares(self) -> list[AgentMiddleware[object, object]] | None:
        return None
