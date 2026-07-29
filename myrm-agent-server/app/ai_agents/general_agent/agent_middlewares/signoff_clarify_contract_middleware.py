"""Signoff clarify contract — deterministic ask_question on first turn (M3 E2E).

[INPUT]
- engineParams.signoffClarifyContract (POS: Request flag for M3 signoff pool)

[OUTPUT]
- SignoffClarifyContractMiddleware: H2d deterministic stub model on first turn

[POS]
General agent middleware for clarify signoff E2E contract (zero LLM on first turn).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from app.ai_agents.general_agent.signoff_clarify_contract_core import (
    build_signoff_clarify_deterministic_model,
)

logger = logging.getLogger(__name__)

_ASK_QUESTION_TOOL = "ask_question_tool"


class SignoffClarifyContractMiddleware(AgentMiddleware):  # type: ignore[type-arg]
    """First-turn ask_question_tool for M3 signoff clarify SHPOIB pool."""

    name = "signoff_clarify_contract_middleware"

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        raise NotImplementedError(
            "SignoffClarifyContractMiddleware does not support synchronous wrap_model_call"
        )

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if not self._enabled:
            return await handler(request)

        state = request.state
        raw_messages = state.get("messages", [])
        messages: list[object] = raw_messages if isinstance(raw_messages, list) else []

        if any(isinstance(msg, AIMessage) for msg in messages):
            return await handler(request)

        if not any(isinstance(msg, HumanMessage) for msg in messages):
            return await handler(request)

        tool_names: set[str] = set()
        for tool in request.tools or []:
            name = getattr(tool, "name", None)
            if isinstance(name, str) and name:
                tool_names.add(name)
            elif isinstance(tool, dict):
                raw_name = tool.get("name")
                if isinstance(raw_name, str):
                    tool_names.add(raw_name)

        if _ASK_QUESTION_TOOL not in tool_names:
            raise RuntimeError(
                "SignoffClarifyContractMiddleware: ask_question_tool not mounted; "
                "enable_structured_clarify/signoff mount bypass required"
            )

        logger.info(
            "SignoffClarifyContractMiddleware: H2d deterministic stub model (no LLM)",
        )
        request = request.override(model=build_signoff_clarify_deterministic_model())
        return await handler(request)


def build_signoff_clarify_contract_middleware(
    *, enabled: bool
) -> SignoffClarifyContractMiddleware:
    return SignoffClarifyContractMiddleware(enabled=enabled)
