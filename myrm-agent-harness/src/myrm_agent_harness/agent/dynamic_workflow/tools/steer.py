"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- SteerChildTool: 向运行中的子 Agent 注入纠正消息

[POS]
`dynamic_workflow/tools/` 的运行时 steer 工具。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class SteerChildInput(BaseModel):
    """Input schema for myrm_tools.steer_child mid-run subagent steering."""

    model_config = ConfigDict(extra="ignore")

    task_id: str = Field(
        ...,
        description="The unique task_id of the target sub-agent to steer.",
    )
    message: str = Field(
        ...,
        description="Corrective or follow-up instruction message injected into the sub-agent's next turn.",
        max_length=4000,
    )
    config_overlay: dict[str, object] | None = Field(
        default=None,
        description="Optional Continual configuration overrides (timeout_seconds, retry_attempts, verification_mode, etc.) applied in-flight.",
    )

class SteerChildTool(BaseTool):
    """PTC tool that injects steering messages into a child subagent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "steer_child"
    description: str = (
        "Inject a corrective or follow-up instruction into a running or active child sub-agent. "
        "Allows dynamic redirection in multi-stage workflows without cold-respawning."
    )
    args_schema: type[BaseModel] = SteerChildInput

    parent_agent: object

    def _run(
        self,
        task_id: str,
        message: str,
        config_overlay: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if not hasattr(self.parent_agent, "steer_child"):
            return {
                "success": False,
                "task_id": task_id,
                "error": "Parent agent does not support steer_child.",
            }
        try:
            if config_overlay is not None:
                steered = self.parent_agent.steer_child(task_id, message, config_overlay=config_overlay)
            else:
                steered = self.parent_agent.steer_child(task_id, message)
        except TypeError:
            steered = self.parent_agent.steer_child(task_id, message)
        if steered:
            return {
                "success": True,
                "task_id": task_id,
                "message": f"Steering message successfully queued for sub-agent `{task_id}`.",
            }
        return {
            "success": False,
            "task_id": task_id,
            "error": f"Could not steer `{task_id}`: sub-agent not found or already completed.",
        }

    async def _arun(
        self,
        task_id: str,
        message: str,
        config_overlay: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._run(task_id=task_id, message=message, config_overlay=config_overlay)
