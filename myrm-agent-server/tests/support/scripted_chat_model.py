"""A chat model that answers every prompt with a fixed reply, for tests of code that distils text with an LLM.

``ScriptedChatModel`` is a real ``BaseChatModel``, so call sites type-check against the production signatures without a
cast; ``calls`` counts the prompts it was asked.
"""

from __future__ import annotations

import asyncio

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    """Replies ``reply`` to every prompt and counts the prompts in ``calls``."""

    reply: str
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        # Yields to the event loop like a network call would, so concurrent callers overlap.
        await asyncio.sleep(0)
        return self._generate(messages, stop)
