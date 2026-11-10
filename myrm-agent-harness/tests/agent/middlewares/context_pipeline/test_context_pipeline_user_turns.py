"""What the context pipeline middleware tells its processors about the history: the user's turns and the re-read files.

A notice the runtime appended is not a turn of the user's, and a file path the pipeline reports as freshly re-read has to
be a path the guard can open.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict, cast
from unittest.mock import AsyncMock, MagicMock, patch

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.context_management.pipeline import ProcessorContext
from myrm_agent_harness.agent.middlewares.context_pipeline.context_pipeline_middleware import (
    create_context_pipeline_middleware,
)
from myrm_agent_harness.core.message_origin import runtime_human_message

_GUARDS = "myrm_agent_harness.agent.meta_tools.file_ops.core.file_integrity_guard._integrity_guards"
_LOOP_GUARD = "myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware.notify_loop_guard_compaction"
_EVENTS = "myrm_agent_harness.utils.event_utils.dispatch_custom_event"


class _RunContext(TypedDict):
    chat_id: str
    max_context_tokens: int


class _RecordingGuard:
    """Stands in for a read-before-edit guard: remembers what was registered as read."""

    def __init__(self) -> None:
        self.registered: list[object] = []

    def clear(self) -> None:
        self.registered.clear()

    def record_read(self, path: object, content: str) -> None:
        self.registered.append(path)


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


def _processed(messages: Sequence[BaseMessage], **overrides: object) -> ProcessorContext:
    context = ProcessorContext(messages=list(messages), user_query="", user_id="user-1", chat_id="chat-1", llm=_llm())
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


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


async def test_only_paths_given_as_text_are_registered_as_read_after_a_compaction(tmp_path: Path) -> None:
    kept, foreign = tmp_path / "kept.txt", tmp_path / "foreign.txt"
    kept.write_text("kept", encoding="utf-8")
    foreign.write_text("foreign", encoding="utf-8")
    guard = _RecordingGuard()
    pipeline = MagicMock()
    pipeline.process = AsyncMock(
        return_value=_processed(
            _history(),
            tokens_saved=500,
            operations=["compress"],
            metadata={"post_compaction_reread_files": [str(kept), foreign]},
        )
    )

    with patch(_GUARDS, {"chat-1": guard}), patch(_LOOP_GUARD), patch(_EVENTS, new_callable=AsyncMock):
        await _run(pipeline)

    assert guard.registered == [str(kept)]
