"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- HumanAskTool / AskGateCallable: 工作流中途人工输入

[POS]
`dynamic_workflow/tools/` 的 human-in-the-loop 工具。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

AskGateCallable = Callable[[str, list[str], int, str], Awaitable[str | None]]

class HumanAskInput(BaseModel):
    """Input schema for myrm_tools.human_ask mid-run human-in-the-loop gate."""

    model_config = ConfigDict(extra="ignore")

    question: str = Field(
        ...,
        description="The question or decision prompt to present to the user.",
    )
    options: list[str] = Field(
        default_factory=list,
        description="Optional list of discrete options for multiple-choice decisions (e.g. ['continue', 'abort']).",
    )
    timeout_seconds: int = Field(
        default=300,
        description="Timeout in seconds to wait for user input (default 300s). Falls back to default_action on timeout.",
    )
    default_action: str = Field(
        default="",
        description="Fallback answer or action if user response times out.",
    )

class HumanAskTool(BaseTool):
    """PTC tool that suspends the Dynamic Workflow execution and requests mid-run user input via PhaseWaiter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "human_ask"
    description: str = (
        "Ask the user a question or present a critical decision during Dynamic Workflow execution. "
        "Suspends workflow execution until the user responds or timeout elapses."
    )
    args_schema: type[BaseModel] = HumanAskInput

    event_queue: asyncio.Queue[dict[str, object]]
    message_id: str = ""
    ask_gate_callable: AskGateCallable | None = None
    cancel_token: CancellationToken | None = None

    def _run(
        self,
        question: str,
        options: list[str] | None = None,
        timeout_seconds: int = 300,
        default_action: str = "",
    ) -> object:
        raise NotImplementedError("HumanAskTool only supports async execution.")

    async def _arun(
        self,
        question: str,
        options: list[str] | None = None,
        timeout_seconds: int = 300,
        default_action: str = "",
    ) -> dict[str, object]:
        if self.cancel_token and self.cancel_token.is_cancelled:
            return {
                "success": False,
                "answer": default_action or None,
                "error": "Workflow cancelled by user before human_ask",
                "timed_out": False,
            }

        opts = options or []
        timeout_sec = max(5, min(timeout_seconds, 1800))

        # 1. Emit human_gate status event to frontend SSE
        gate_event: dict[str, object] = {
            "type": "status",
            "messageId": self.message_id,
            "data": {
                "phase": "human_gate",
                "status": "waiting",
                "question": question,
                "options": opts,
                "timeout_seconds": timeout_sec,
                "default_action": default_action,
                "source": "dynamic_workflow",
            },
        }
        await self.event_queue.put(gate_event)

        # 2. Invoke server-provided approval gate (PhaseWaiter bridge)
        answer: str | None = None
        timed_out = False
        error_msg = ""

        try:
            if self.ask_gate_callable is not None:
                answer = await self.ask_gate_callable(question, opts, timeout_sec, default_action)
            else:
                # Direct fallback when gate callable is not injected (e.g. unattended tests)
                logger.info(
                    "HumanAskTool has no server ask_gate_callable; using default_action='%s'",
                    default_action,
                )
                answer = default_action or (opts[0] if opts else "continue")
        except TimeoutError:
            timed_out = True
            answer = default_action
            error_msg = f"User response timed out after {timeout_sec}s; applied default: '{default_action}'"
            logger.warning(
                "HumanAskTool timed out: message_id=%s, applied default='%s'",
                self.message_id,
                default_action,
            )
        except Exception as exc:
            error_msg = f"human_ask failed: {exc}"
            logger.error("HumanAskTool error: %s", exc, exc_info=True)

        # 3. Emit resolved status event to frontend SSE
        resolved_event: dict[str, object] = {
            "type": "status",
            "messageId": self.message_id,
            "data": {
                "phase": "human_gate",
                "status": "resolved",
                "answer": answer,
                "timed_out": timed_out,
                "source": "dynamic_workflow",
            },
        }
        await self.event_queue.put(resolved_event)

        return {
            "success": error_msg == "",
            "answer": answer,
            "error": error_msg,
            "timed_out": timed_out,
        }
