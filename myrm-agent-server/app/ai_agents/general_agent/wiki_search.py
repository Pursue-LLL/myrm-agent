"""BM25 search backend injected into the wiki query engine.

[INPUT]
- myrm_agent_harness.toolkits.wiki::WikiStructure, SemanticSearchFn (POS: concept file listing, search-backend contract)
- myrm_agent_harness.toolkits.retriever.bm25_retrieval::bm25_retrieval (POS: one-shot BM25 ranking)

[OUTPUT]
- build_wiki_bm25_search_fn(): a ``SemanticSearchFn`` ranking the agent's wiki concept articles

[POS]
Server-side wiki search backend. The query engine calls the backend as ``(query, top_n)``, so the
backend resolves its own corpus (the agent vault plus shared read-only vaults) instead of receiving paths.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from myrm_agent_harness.toolkits.retriever.bm25_retrieval import bm25_retrieval
from myrm_agent_harness.toolkits.wiki import SemanticSearchFn, WikiStructure


def build_wiki_bm25_search_fn(base_dir: Path | str, public_dirs: list[Path | str]) -> SemanticSearchFn:
    """Build a BM25 backend over every concept article visible to the agent.

    BM25 weights terms by TF-IDF with length normalisation, which ranks concept articles better than
    keyword overlap. Files are read per call so articles written during the session are searchable.
    """
    structure = WikiStructure(base_dir, public_dirs)

    def _rank(query: str, top_n: int) -> list[tuple[Path, float]]:
        paths: list[Path] = []
        texts: list[str] = []
        for path in structure.list_concepts():
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            paths.append(path)

        if not texts:
            return []

        scored = bm25_retrieval(texts, query, top_k=top_n, only_relevant=True)
        return [(paths[idx], score) for idx, score in scored]

    async def _search(query: str, top_n: int) -> list[tuple[Path, float]]:
        # File reads and scoring are blocking; keep them off the event loop.
        return await asyncio.to_thread(_rank, query, top_n)

    return _search
