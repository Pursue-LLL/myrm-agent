"""A filtered grep/glob listing keeps its real first and last rows instead of an invented outline."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.context_management.infra.schemas import DEFAULT_CONTEXT_CONFIG
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.filter_processor import FilterProcessor
from myrm_agent_harness.agent.context_management.strategies.filter import (
    ROW_LISTING_TOOLS,
    create_filtered_result,
    should_filter,
)
from myrm_agent_harness.agent.context_management.strategies.filters.row_sample_filter import ROW_SAMPLE_MAX_CHARS
from myrm_agent_harness.agent.meta_tools.file_search.glob_tool import create_glob_tool
from myrm_agent_harness.agent.meta_tools.file_search.grep_tool import create_grep_tool
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var
from myrm_agent_harness.utils.text_utils import get_token_count


def _grep_listing() -> str:
    """Output shaped like grep_tool with context lines: a path line, then ``N:`` match and ``N-`` context rows."""
    rows = ["Found 100 match(es) for 'import':", ""]
    for index in range(100):
        rows.append(f"src/pkg/module_{index:03d}.py")
        rows.extend(f"  {line}- context row {index}.{line}" for line in range(10, 13))
        rows.append(f"  13: from pkg.shared import helper_{index}, other_{index}")
        rows.extend(f"  {line}- context row {index}.{line}" for line in range(14, 17))
        rows.append("")
    rows.append("... (limited to first 100 results)")
    return "\n".join(rows)


def _glob_listing() -> str:
    return "\n".join(f"src/pkg/part_{index % 40:02d}/module_{index:04d}.py" for index in range(1200))


LISTINGS = [("grep_tool", _grep_listing), ("glob_tool", _glob_listing)]


@contextmanager
def _evicted_scope(workspace: str, chat_id: str) -> Iterator[None]:
    workspace_token = workspace_root_var.set(workspace)
    chat_token = chat_id_var.set(chat_id)
    try:
        yield
    finally:
        workspace_root_var.reset(workspace_token)
        chat_id_var.reset(chat_token)


def _tool_context(tool_name: str, listing: str) -> ProcessorContext:
    return ProcessorContext(
        messages=[ToolMessage(content=listing, tool_call_id="call-1", name=tool_name)],
        user_query="find the imports",
        llm=None,
    )


def test_row_listing_tools_are_the_names_of_the_search_tools() -> None:
    """A renamed search tool must fail here instead of silently falling back to an invented outline."""
    assert {create_grep_tool().name, create_glob_tool().name} == ROW_LISTING_TOOLS


class TestRowListingResult:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool_name", "make_listing"), LISTINGS)
    async def test_first_and_last_rows_are_shown_exactly_as_returned(
        self, tool_name: str, make_listing: Callable[[], str]
    ) -> None:
        listing = make_listing()
        assert should_filter(listing, threshold=DEFAULT_CONTEXT_CONFIG.tool_result_evict_threshold)

        result = await create_filtered_result(listing, "saved.txt", "find the imports", tool_name=tool_name)

        rows = listing.splitlines()
        shown = result.structure_overview
        assert rows[0] in shown
        assert rows[-1] in shown
        assert len(shown) <= ROW_SAMPLE_MAX_CHARS
        assert "[Truncated:" in shown
        row_set = set(rows)
        invented = [row for row in shown.splitlines() if row.strip() and not row.startswith("[Truncated:")]
        assert [row for row in invented if row not in row_set] == []

    @pytest.mark.asyncio
    async def test_counts_describe_the_whole_listing_not_the_sample(self) -> None:
        listing = _grep_listing()

        result = await create_filtered_result(listing, "saved.txt", "q", tool_name="grep_tool")

        assert result.total_lines == len(listing.splitlines())
        assert result.total_chars == len(listing)
        assert result.estimated_tokens == get_token_count(listing)

    @pytest.mark.asyncio
    async def test_a_listing_that_mentions_code_words_is_not_typed_as_code(self) -> None:
        listing = _grep_listing()

        result = await create_filtered_result(listing, "saved.txt", "q", tool_name="grep_tool")

        assert result.content_type == "plain_text"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool_name", "make_listing"), LISTINGS)
    async def test_no_llm_is_asked_to_summarise_a_listing(
        self, tool_name: str, make_listing: Callable[[], str]
    ) -> None:
        llm = AsyncMock(spec=BaseChatModel)

        result = await create_filtered_result(make_listing(), "saved.txt", "q", llm=llm, tool_name=tool_name)

        assert llm.mock_calls == []
        assert result.llm_generated is False

    @pytest.mark.asyncio
    async def test_other_tools_are_filtered_as_before(self) -> None:
        listing = _grep_listing()

        unnamed = await create_filtered_result(listing, "saved.txt", "q")
        named = await create_filtered_result(listing, "saved.txt", "q", tool_name="web_search_tool")
        listing_tool = await create_filtered_result(listing, "saved.txt", "q", tool_name="grep_tool")

        assert named == unnamed
        assert listing_tool != unnamed


class TestFilterProcessorRowListing:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool_name", "make_listing"), LISTINGS)
    async def test_message_carries_real_rows_and_the_full_copy_stays_on_disk(
        self, tmp_path: Path, tool_name: str, make_listing: Callable[[], str]
    ) -> None:
        listing = make_listing()
        rows = listing.splitlines()
        middle = next(row for row in rows[len(rows) // 2 :] if row.strip())

        with _evicted_scope(str(tmp_path), "chat-1"):
            result = await FilterProcessor().process(_tool_context(tool_name, listing))

        saved = list((tmp_path / ".context" / "chat-1" / "evicted").glob("*.txt"))
        assert len(saved) == 1
        rel_path = f".context/chat-1/evicted/{saved[0].name}"
        message = str(result.messages[0].content)
        assert rows[0] in message
        assert rows[-1] in message
        assert middle not in message
        assert middle in saved[0].read_text(encoding="utf-8")
        assert f"Full output saved to: {rel_path}" in message
        assert get_token_count(message) < get_token_count(listing) / 3
        assert result.tokens_saved > 0

    @pytest.mark.asyncio
    async def test_unsaved_listing_still_shows_rows_and_claims_no_copy(self, tmp_path: Path) -> None:
        listing = _grep_listing()
        rows = listing.splitlines()

        with _evicted_scope(str(tmp_path), ""):
            result = await FilterProcessor().process(_tool_context("grep_tool", listing))

        message = str(result.messages[0].content)
        assert rows[0] in message
        assert rows[-1] in message
        assert "NO SAVED COPY" in message
        assert "Full output saved to" not in message
