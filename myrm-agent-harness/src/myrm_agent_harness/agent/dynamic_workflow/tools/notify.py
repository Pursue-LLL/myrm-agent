"""[INPUT]
- agent.skills.mcp.progress_payload::build_workflow_stage_event / normalize_dw_message (POS: 工作流阶段事件)

[OUTPUT]
- NotifyProgressTool: PTC 工作流进度通知

[POS]
`dynamic_workflow/tools/` 的进度通知工具。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from myrm_agent_harness.agent.skills.mcp.progress_payload import (
    build_workflow_stage_event,
    normalize_dw_message,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class NotifyProgressInput(BaseModel):
    message: str = Field(..., description="Status message to display to the user.")
    progress: int = Field(
        default=-1,
        description="Progress percentage (0-100). Use -1 for indeterminate.",
    )
    step_index: int = Field(
        default=0,
        description="Current step number (1-based). 0 if not applicable.",
    )
    total_steps: int = Field(
        default=0,
        description="Total number of steps. 0 if not applicable.",
    )
    category: str = Field(
        default="",
        description="Stage/phase label (e.g. 'data_collection', 'analysis'). Groups related notifications.",
    )
    level: str = Field(
        default="info",
        description="Notification level: 'info' (normal), 'warn' (attention), or 'alert' (critical).",
    )

class NotifyProgressTool(BaseTool):
    """PTC tool that emits real-time workflow stage progress events to the frontend SSE stream."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "notify"
    description: str = (
        "Report workflow stage progress to the user interface. "
        "Call this at the start of each major phase to show real-time progress."
    )
    args_schema: type[BaseModel] = NotifyProgressInput

    event_queue: asyncio.Queue[dict[str, object]]
    message_id: str = ""

    def _run(
        self,
        message: str,
        progress: int = -1,
        step_index: int = 0,
        total_steps: int = 0,
        category: str = "",
        level: str = "info",
    ) -> object:
        raise NotImplementedError("NotifyProgressTool only supports async execution.")

    async def _arun(
        self,
        message: str,
        progress: int = -1,
        step_index: int = 0,
        total_steps: int = 0,
        category: str = "",
        level: str = "info",
    ) -> object:
        event = build_workflow_stage_event(
            self.message_id,
            message,
            progress=progress,
            step_index=step_index,
            total_steps=total_steps,
            category=category,
            level=level,
        )
        await self.event_queue.put(event)
        display_message = normalize_dw_message(message)
        return {"success": True, "message": display_message}
