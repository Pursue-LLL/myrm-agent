"""A tool result the TTL prune archives is offloaded once, handed to the summary service once and replaced by a reference.

The archive step is the one part of the prune that talks to the offload store and the summary service, so these cases
run it through the processor with both in place and check what each of them is given.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig

from myrm_agent_harness.agent.context_management.archive_checkpoint import ArchiveSummaryService
from myrm_agent_harness.agent.context_management.infra.schemas import CacheTtlPruneConfig, ContextOffloadResult
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.cache_ttl_prune_archive import (
    _OFFLOAD_IDEMPOTENCY_CACHE_LIMIT,
    ToolResultArchiver,
)
from myrm_agent_harness.agent.context_management.pipeline.processors.cache_ttl_prune_processor import (
    CacheTtlPruneProcessor,
)

# A window this small puts any tool result past the hard-clear ratio, so the pass archives it.
_ARCHIVE_NOW = CacheTtlPruneConfig(
    soft_trim_ratio=0.01, hard_clear_ratio=0.02, min_prunable_tokens=100, keep_last_assistant_turns=0
)
_PAYLOAD = "x" * 5000


class _Store:
    """An offload callback that remembers what it was asked to store."""

    def __init__(self, *, fails: bool = False) -> None:
        self.stored: list[str] = []
        self._fails = fails

    async def __call__(self, *, content: str, tool_name: str, scope_id: str | None) -> str | ContextOffloadResult:
        self.stored.append(content)
        if self._fails:
            return ContextOffloadResult.failure("quota_exceeded", "quota full")
        return f".context/{scope_id}/compacted/{tool_name}.txt"


def _messages() -> list[BaseMessage]:
    return [HumanMessage(content="hi"), ToolMessage(content=_PAYLOAD, tool_call_id="tc_1", name="grep_tool")]


def _context(
    chat_id: str = "chat-1",
    *,
    summarizer_llm: BaseChatModel | None = None,
    metadata: dict[str, object] | None = None,
) -> ProcessorContext:
    return ProcessorContext(
        messages=_messages(),
        user_query="test",
        chat_id=chat_id,
        summarizer_llm=summarizer_llm,
        metadata=metadata or {},
        merged_context={},
    )


def _processor(store: _Store, service: MagicMock) -> CacheTtlPruneProcessor:
    return CacheTtlPruneProcessor(
        config=_ARCHIVE_NOW, max_context_tokens=1000, on_prune_offload=store, archive_summary_service=service
    )


async def test_an_archived_result_is_handed_to_the_summary_service() -> None:
    service = MagicMock(spec=ArchiveSummaryService)
    summarizer = MagicMock()
    result = await _processor(_Store(), service).process(_context(summarizer_llm=summarizer))

    assert "result archived" in str(result.messages[1].content)
    service.dispatch.assert_called_once_with(
        tool_name="grep_tool",
        content=_PAYLOAD,
        archive_path=".context/chat-1/compacted/grep_tool.txt",
        chat_id="chat-1",
        summarizer_llm=summarizer,
        tool_call_id="tc_1",
        runnable_config=None,
    )


async def test_the_run_config_goes_with_the_summary_job() -> None:
    service = MagicMock(spec=ArchiveSummaryService)
    run_config = RunnableConfig(tags=["run"])

    await _processor(_Store(), service).process(_context(metadata={"runnable_config": run_config}))

    assert service.dispatch.call_args.kwargs["runnable_config"] == run_config


async def test_a_result_archived_again_is_stored_and_handed_over_once() -> None:
    store, service = _Store(), MagicMock(spec=ArchiveSummaryService)
    processor = _processor(store, service)

    await processor.process(_context())
    again = await processor.process(_context())

    assert store.stored == [_PAYLOAD]
    assert "result archived" in str(again.messages[1].content)
    service.dispatch.assert_called_once()


async def test_the_same_result_in_another_chat_is_stored_again() -> None:
    store = _Store()
    processor = _processor(store, MagicMock(spec=ArchiveSummaryService))

    await processor.process(_context("chat-1"))
    await processor.process(_context("chat-2"))

    assert store.stored == [_PAYLOAD, _PAYLOAD]


async def test_what_the_archiver_remembers_for_a_retry_is_bounded() -> None:
    store = _Store()
    archiver = ToolResultArchiver(store, estimate_tokens=len, on_stored=lambda *_: None)
    context = _context()

    async def archive(number: int) -> None:
        text = str(number)
        message = ToolMessage(content=text, tool_call_id=f"tc_{number}", name="grep_tool")
        await archiver.try_archive(msg=message, content=text, context=context)

    for number in range(_OFFLOAD_IDEMPOTENCY_CACHE_LIMIT + 1):
        await archive(number)
    stored = len(store.stored)

    await archive(_OFFLOAD_IDEMPOTENCY_CACHE_LIMIT)
    assert len(store.stored) == stored
    await archive(0)
    assert len(store.stored) == stored + 1


async def test_a_failed_offload_hands_nothing_over_and_the_result_is_trimmed_instead() -> None:
    service = MagicMock(spec=ArchiveSummaryService)

    result = await _processor(_Store(fails=True), service).process(_context())

    assert "Tool result trimmed" in str(result.messages[1].content)
    service.dispatch.assert_not_called()
