"""Hoist a tool result's citation sources out of the text the model reads.

A tool that cites sources returns ``{"content": ..., "metadata": {"sources": [...]}}``. LangChain stringifies that
dict, so the model would read the whole sources list a second time beside ``content``, which already names the same
sources. ``hoist_tool_sources`` moves the list into ``ToolMessage.additional_kwargs``, which no model provider
receives, and leaves the model the rest of the result. ``stamp_source_indexes`` then writes into each hoisted
source the number the run gave it, so the stored tool message records what the model read.

[INPUT]
- langchain_core.messages::ToolMessage (POS: Core message type definitions)
- langgraph.types::Command (POS: A tool call may answer with a graph command instead of a message)
- core.context_vars::SourceIndexer (POS: Cross-layer ContextVar registry; the run's source numbering)

[OUTPUT]
- TOOL_SOURCES_KWARG: The ``additional_kwargs`` key the hoisted sources travel under
- hoist_tool_sources(): Move ``metadata.sources`` out of a ``{content, metadata}`` result
- stamp_source_indexes(): Record the run's number in each hoisted source

[POS]
Last step of tool interception, after every post-call guard has seen the whole result. The streaming layer reads
the sources back from ``additional_kwargs`` and hands them to the run's SourceTracker; the next run of the thread
reads the stamped numbers back from the checkpoint (``agent/streaming/source_numbering.py``).
"""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from myrm_agent_harness.core.context_vars import SourceIndexer

TOOL_SOURCES_KWARG = "sources"

# Cheap pre-filter: most tool results are not an envelope, and most JSON results carry no sources.
_SOURCES_MARKER = '"sources"'


def hoist_tool_sources(result: ToolMessage | Command[object]) -> ToolMessage | Command[object]:
    """Move ``metadata.sources`` of a ``{content, metadata}`` result into ``additional_kwargs``.

    The model then reads ``content`` alone when nothing else is left in the envelope, and otherwise the envelope
    without its sources. Anything that is not such an envelope (plain text, an error result, a graph command,
    JSON of another shape, an envelope a guard appended text to) is returned as it is.
    """
    if not isinstance(result, ToolMessage) or result.status == "error":
        return result
    text = result.content
    if not isinstance(text, str) or not text.startswith("{") or _SOURCES_MARKER not in text:
        return result
    try:
        envelope = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        # Output that merely resembles JSON, or nests too deeply to parse, is still a successful result: an exception
        # escaping here would make the interceptor report the tool call as failed.
        return result
    content = envelope.get("content")
    metadata = envelope.get("metadata")
    if not isinstance(content, str) or not isinstance(metadata, dict):
        return result
    sources = metadata.get("sources")
    if not isinstance(sources, list):
        return result

    remaining_metadata = {key: value for key, value in metadata.items() if key != "sources"}
    kept = {
        key: remaining_metadata if key == "metadata" else value
        for key, value in envelope.items()
        if key != "metadata" or remaining_metadata
    }
    update: dict[str, object] = {
        "content": content if kept.keys() == {"content"} else json.dumps(kept, ensure_ascii=False)
    }
    if sources:
        update["additional_kwargs"] = {**result.additional_kwargs, TOOL_SOURCES_KWARG: sources}
    return result.model_copy(update=update)


def stamp_source_indexes(
    result: ToolMessage | Command[object], index_for: SourceIndexer | None
) -> ToolMessage | Command[object]:
    """Write the number the run gave each hoisted source into it: the number the model read, and its card's index.

    The number is asked of the run's numbering the way the tool asked it, so a source the tool numbered keeps that
    number. Anything without hoisted sources, and a run that numbers nothing, is returned as it is.
    """
    if index_for is None or not isinstance(result, ToolMessage):
        return result
    sources = result.additional_kwargs.get(TOOL_SOURCES_KWARG)
    if not isinstance(sources, list) or not sources:
        return result
    stamped = [{**source, "index": index_for(source)} if isinstance(source, dict) else source for source in sources]
    return result.model_copy(update={"additional_kwargs": {**result.additional_kwargs, TOOL_SOURCES_KWARG: stamped}})
