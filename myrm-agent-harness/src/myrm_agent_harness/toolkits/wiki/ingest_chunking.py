"""Large-document chunking for Wiki ingestion.

[INPUT]
- toolkits.retriever.splitter::TextChunker (POS: Token-aware text splitter)
- utils.logger_utils::get_agent_logger (POS: Agent logger)

[OUTPUT]
- split_if_large: a document's (relative_path, content) pieces, one entry when it is small

[POS]
Keeps each raw/ source small enough for the compile stage: a document above the threshold is cut into numbered
chunk files next to its original path.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

_LARGE_DOC_CHUNK_THRESHOLD = 80_000


def split_if_large(content: str, base_path: str) -> list[tuple[str, str]]:
    """Split large content into chunks for better wiki compilation.

    Returns list of (relative_path, content) tuples. For small documents,
    returns a single entry with the original path.
    """
    if len(content) <= _LARGE_DOC_CHUNK_THRESHOLD:
        return [(base_path, content)]

    from myrm_agent_harness.toolkits.retriever.splitter import TextChunker

    chunker = TextChunker(min_chunk_tokens=200)
    docs = chunker.chunk_text(content, document_metadata={"title": Path(base_path).stem})

    if len(docs) <= 1:
        return [(base_path, content)]

    stem = Path(base_path).stem
    parent = str(Path(base_path).parent) if Path(base_path).parent != Path(".") else ""
    results: list[tuple[str, str]] = []

    for i, doc in enumerate(docs, 1):
        chunk_name = f"{stem}_chunk{i:03d}.md"
        chunk_path = f"{parent}/{chunk_name}" if parent else chunk_name
        results.append((chunk_path, doc.page_content))

    logger.info(f"Split large document into {len(results)} chunks: {stem}")
    return results
