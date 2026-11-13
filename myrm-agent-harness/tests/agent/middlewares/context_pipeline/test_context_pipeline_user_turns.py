"""What the context pipeline middleware tells its processors about the history: the user's turns.

A notice the runtime appended is not a turn of the user's.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict, cast
from unittest.mock import AsyncMock, MagicMock

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.context_management.pipeline import ProcessorContext
from myrm_agent_harness.agent.middlewares.context_pipeline.context_pipeline_middleware import (
    create_context_pipeline_middleware,
)
from myrm_agent_harness.core.message_origin import runtime_human_message


class _RunContext(TypedDict):
    chat_id: str
    max_context_tokens: int


def _llm() -> MagicMock:
    llm = MagicMock()
    llm.model = "test-model"
    llm.api_base = ""
    return llm


def _history() -> list[AnyMessage]:
    return [
        HumanMessage(content="first"),
        AIMessage(content="answer"),
        HumanMessage(content="second"),
        runtime_human_message("[constraint] the sandbox has no network"),
    ]


def _processed(messages: Sequence[BaseMessage]) -> ProcessorContext:
    return ProcessorContext(messages=list(messages), user_query="", user_id="user-1", chat_id="chat-1", llm=_llm())


async def _run(pipeline: MagicMock) -> None:
    llm = _llm()
    context = _RunContext(chat_id="chat-1", max_context_tokens=128_000)
    request = ModelRequest(model=llm, messages=_history(), runtime=Runtime(context=context))
    middleware = create_context_pipeline_middleware(llm=llm, pipeline=pipeline)
    # The middleware reads its run context as a mapping; the request type only names the context its agent declares.
    await middleware.awrap_model_call(
        cast("ModelRequest[None]", request), AsyncMock(return_value=ModelResponse(result=[]))
    )


async def test_the_processors_are_told_how_many_messages_the_user_wrote() -> None:
    pipeline = MagicMock()
    pipeline.process = AsyncMock(return_value=_processed(_history()))

    await _run(pipeline)

    seen: ProcessorContext = pipeline.process.await_args.args[0]
    assert seen.metadata["turn_count"] == 2
