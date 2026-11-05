"""memory_manage MCP tool: update / delete / correct / rate existing memories.

[INPUT]
- toolkits.memory.agent_surface.memory_manage_core::{MANAGE_ACTIONS, manage_memory} (POS: id-addressed manage actions shared with the agent tool)
- toolkits.memory.agent_surface.mcp_server.common::ManagerResolver (POS: Stateless helpers for the recall/list/store/manage tool handlers)
- toolkits.memory.agent_surface.write_failure_feedback (POS: LLM-readable write failure messages)

[OUTPUT]
- register_manage_tool: register memory_manage on an MCPServer

[POS]
Write plane (modify / remove) of the MCP adapter; creation lives in store_tool.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server.common import ManagerResolver
from myrm_agent_harness.toolkits.memory.agent_surface.memory_manage_core import MANAGE_ACTIONS, manage_memory
from myrm_agent_harness.toolkits.memory.agent_surface.write_failure_feedback import write_failure_feedback


def register_manage_tool(mcp: MCPServer, resolve: ManagerResolver, *, description: str) -> None:
    """Register memory_manage on ``mcp``; ``resolve`` supplies the request's MemoryManager."""

    @mcp.tool(name="memory_manage", description=description)
    async def memory_manage(
        action: str,
        memory_id: str,
        new_content: str | None = None,
        new_importance: float | None = None,
        rating_score: int | None = None,
    ) -> str:
        """Manage an existing memory.

        Args:
            action: "update", "delete", "correct", or "rate".
            memory_id: Memory ID from memory_recall results.
            new_content: Required for update/correct actions.
            new_importance: Optional new importance score (0.0-1.0).
            rating_score: Required for rate action (1-5, 1=bad, 5=excellent).
        """
        if action not in MANAGE_ACTIONS:
            return f"Error: invalid action '{action}'. Valid: {', '.join(MANAGE_ACTIONS)}"

        mgr = resolve()
        try:
            return await manage_memory(
                mgr,
                action=action,
                memory_id=memory_id,
                new_content=new_content,
                new_importance=new_importance,
                rating_score=rating_score,
            )
        except Exception as e:
            return write_failure_feedback(
                "MCP memory_manage", e, fallback="Failed to manage memory", memory_id=memory_id
            )
