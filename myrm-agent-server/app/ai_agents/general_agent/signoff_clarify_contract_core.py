"""Signoff clarify contract SSOT — deterministic ask_question form for M3 E2E.

[INPUT]
- langchain_core BaseChatModel (POS: stub LLM for deterministic E2E path)

[OUTPUT]
- SignoffClarifyContractStubModel: fake chat model emitting tool_call for ask_question
- SIGNOFF_CLARIFY_FORM_ARGS: canonical form payload
- is_signoff_clarify_enabled: gate predicate for the contract path
- build_signoff_clarify_response: assemble expected clarify response

[POS]
Active when request carries engineParams.signoffClarifyContract=true.
H2d: middleware always uses deterministic stub on first turn; tool mount bypasses
unattended/structured_clarify gates when signoff_clarify_contract is set.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Final

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_ASK_QUESTION_TOOL: Final[str] = "ask_question_tool"

SIGNOFF_CLARIFY_FORM_ARGS: Final[dict[str, object]] = {
    "title": "Pick stack",
    "requires_confirmation": False,
    "questions": [
        {
            "id": "stack",
            "prompt": "Which stack?",
            "options": [
                {"id": "a", "label": "Option A"},
                {"id": "b", "label": "Option B"},
            ],
            "allow_multiple": False,
        }
    ],
}


def signoff_clarify_pool_active() -> bool:
    return os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1"


def signoff_clarify_contract_enabled(*, flag: bool = False) -> bool:
    """True when request flag or SHPOIB signoff pool env activates the contract."""
    return flag or signoff_clarify_pool_active()


def build_signoff_clarify_ai_message() -> AIMessage:
    """Synthetic first-turn tool call — matches M3 signoff E2E prompt contract."""
    tool_call_id = f"signoff_clarify_{uuid.uuid4().hex[:12]}"
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": tool_call_id,
                "name": _ASK_QUESTION_TOOL,
                "args": dict(SIGNOFF_CLARIFY_FORM_ARGS),
            }
        ],
    )


class SignoffClarifyDeterministicChatModel(BaseChatModel):
    """Stub LLM that always emits the signoff ask_question_tool call."""

    @property
    def _llm_type(self) -> str:
        return "signoff_clarify_deterministic"

    def bind_tools(
        self,
        tools: object,
        *,
        tool_choice: object | None = None,
        **kwargs: object,
    ) -> SignoffClarifyDeterministicChatModel:
        """LangChain agent factory requires bind_tools when tools are mounted."""
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = build_signoff_clarify_ai_message()
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = build_signoff_clarify_ai_message()
        return ChatResult(generations=[ChatGeneration(message=message)])


def build_signoff_clarify_deterministic_model() -> SignoffClarifyDeterministicChatModel:
    return SignoffClarifyDeterministicChatModel()
