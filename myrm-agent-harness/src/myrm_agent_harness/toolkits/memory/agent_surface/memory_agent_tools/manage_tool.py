"""memory_manage_tool: update / delete / correct / rate existing memories.

[INPUT]
- toolkits.memory.agent_surface.memory_manage_core::{ManageAction, manage_memory} (POS: id-addressed manage actions shared with the MCP adapter)
- toolkits.memory.manager::MemoryManager (POS: memory lifecycle manager; protected memories are never touched by the agent)
- toolkits.memory.agent_surface.write_failure_feedback (POS: LLM-readable write failure messages)

[OUTPUT]
- MemoryManageInput: pydantic args schema of memory_manage_tool
- build_memory_manage_tool: bind memory_manage_tool to a manager

[POS]
Write plane (modify / remove) of the agent memory tools; creation lives in save_tool.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from myrm_agent_harness.toolkits.memory.agent_surface.memory_manage_core import ManageAction, manage_memory
from myrm_agent_harness.toolkits.memory.agent_surface.write_failure_feedback import write_failure_feedback
from myrm_agent_harness.toolkits.memory.manager import MemoryManager


class MemoryManageInput(BaseModel):
    action: ManageAction = Field(
        description="update: wording/importance; correct: wrong knowledge; delete; rate",
    )
    memory_id: str = Field(description="Memory ID from memory_search_tool results.")
    new_content: str | None = Field(
        default=None,
        description=("Required for update (wording/importance) and correct (wrong fact, knowledge only)."),
    )
    new_importance: float | None = Field(
        default=None,
        description="Optional new importance for update.",
    )
    rating_score: int | None = Field(
        default=None,
        description="Required for rate; integer 1-5.",
    )


def build_memory_manage_tool(manager: MemoryManager, *, description: str) -> BaseTool:
    """Create memory_manage_tool bound to ``manager``."""

    @tool("memory_manage_tool", description=description, args_schema=MemoryManageInput)
    async def memory_manage(
        action: ManageAction,
        memory_id: str,
        new_content: str | None = None,
        new_importance: float | None = None,
        rating_score: int | None = None,
    ) -> str:
        """Update, delete, correct, or rate an existing memory entry."""
        try:
            return await manage_memory(
                manager,
                action=action,
                memory_id=memory_id,
                new_content=new_content,
                new_importance=new_importance,
                rating_score=rating_score,
            )
        except Exception as e:
            return write_failure_feedback("memory_manage", e, fallback="Failed to manage memory", memory_id=memory_id)

    return memory_manage
