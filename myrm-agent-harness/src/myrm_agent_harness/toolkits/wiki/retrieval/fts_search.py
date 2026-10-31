"""Wiki index read operations (SQLite FTS5 + Qdrant hybrid search).

[INPUT]
- sqlite3 (POS: standard library database)
- myrm_agent_harness.toolkits.retriever.embedding.window_policy::EmbedInputTooLargeError (POS: embedding input window violation)
- myrm_agent_harness.toolkits.retriever.fusion_strategies::rrf_fusion (POS: result fusion strategy)
- myrm_agent_harness.utils.db.fts5::fts5_auto_heal, relevance_from_rank (POS: FTS5 corruption auto-heal and rank relevance)
- ..core.config::WikiConfig (POS: wiki configuration center)
- ..core.frontmatter_contract::WikiPublishStatus (POS: publish_status SSOT)
- .fts_federation::MAX_FEDERATED_DATABASES, attached_tables (POS: shared index discovery)
- .graph_tables::concept_rows_filter (POS: which index rows are concept pages)
- .sidecar_index::_SIDECAR_PREFIX (POS: L0/L1 sidecar index operations)
- .tokenizer::FTS_TOKENIZER, tokenize_for_fts (POS: table tokenizer and FTS5 query tokenizer)
- .vector_chunks::collapse_vector_hits (POS: L2 chunk vector hit collapsing)

[OUTPUT]
- FtsSearchMixin: FTS5 + vector search/get_truth with the publish_status gate for WikiIndexer; vector hits under another spelling collapse onto the page key
- search_published_index: read-only top published pages of an index file the caller does not own
- index_has_pages: whether such an index file holds any concept page row, so a caller can tell an index that was never filled from a query that matched nothing
- WIKI_FTS_COLUMNS: columns of the wiki_fts table
- create_wiki_fts_table: declare a wiki_fts table with those columns and FTS_TOKENIZER (the one place the table is declared)
- migrate_wiki_fts_schema: rebuild wiki_fts when it predates the search_terms column

[POS]
Wiki index read operations mixin. Keeps hybrid search fusion, the publish gate and
truth lookup apart from the write side in `FtsWriteMixin`, so each module stays
single-responsibility and within size limits. The FTS publish gate is a SQL predicate
of the match query itself, so ranking, LIMIT and OFFSET count published pages only; the
vector side filters its hits after the search because vectors are written for
published pages only.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.retriever.embedding.window_policy import (
    EmbedInputTooLargeError,
)
from myrm_agent_harness.toolkits.retriever.fusion_strategies import rrf_fusion
from myrm_agent_harness.utils.db.fts5 import fts5_auto_heal, relevance_from_rank

from ..core.config import WikiConfig
from ..core.frontmatter_contract import WikiPublishStatus
from .fts_federation import MAX_FEDERATED_DATABASES, attached_tables
from .graph_tables import concept_rows_filter
from .sidecar_index import _SIDECAR_PREFIX
from .tokenizer import FTS_TOKENIZER, tokenize_for_fts
from .vector_chunks import collapse_vector_hits

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from contextlib import AbstractContextManager
    from pathlib import Path

    from myrm_agent_harness.toolkits.memory.protocols.embedding import (
        EmbeddingProtocol,
    )
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol

    from ..core.structure import WikiStructure

logger = logging.getLogger(__name__)


def _published_match_select(conn: sqlite3.Connection, fts_table: str, columns: str) -> str:
    """Build a SELECT over ``fts_table`` (``wiki_fts`` or ``pub_N.wiki_fts``) that yields published pages only.

    The gate belongs in the query: a gate applied to the fetched rows lets drafts fill the LIMIT window and starves
    the caller. Sidecar rows never match. A page without a publish row (a raw interim entry) and an index that
    predates the publish table both read as published, like ``_is_published``.
    """
    schema, _, name = fts_table.rpartition(".")
    qualifier = f"{schema}." if schema else ""
    where = f"{name} MATCH ? AND concept_name NOT GLOB '{_SIDECAR_PREFIX}:*'"
    has_publish_table = conn.execute(
        f"SELECT 1 FROM {qualifier}sqlite_master WHERE type = 'table' AND name = 'wiki_index_meta'"
    ).fetchone()
    if has_publish_table:
        where += (
            f" AND NOT EXISTS (SELECT 1 FROM {qualifier}wiki_index_meta AS meta"
            f" WHERE meta.concept_name = {name}.concept_name"
            f" AND meta.publish_status <> '{WikiPublishStatus.PUBLISHED.value}')"
        )
    return f"SELECT {columns} FROM {fts_table} WHERE {where}"


class FtsSearchMixin:
    """FTS5 truth lookup plus vector search for WikiIndexer.

    Expects the host class to provide: _get_conn, _config, _vector, _embedding,
    _collection_name, _ensure_collection, _structure, _is_sidecar_entry and _index_key.
    """

    _config: WikiConfig
    _vector: VectorStoreProtocol | None
    _embedding: EmbeddingProtocol | None
    _collection_name: str

    if TYPE_CHECKING:
        # Attributes provided by the host class (WikiIndexer); only for type checking.
        _get_conn: Callable[[], AbstractContextManager[sqlite3.Connection]]
        _structure: WikiStructure
        _ensure_collection: Callable[[], Awaitable[None]]
        _is_sidecar_entry: Callable[[str], bool]
        _index_key: Callable[[str], str]

    def _is_published(self, conn: sqlite3.Connection, concept_name: str) -> bool:
        cursor = conn.execute(
            "SELECT publish_status FROM wiki_index_meta WHERE concept_name = ?",
            (concept_name,),
        )
        row = cursor.fetchone()
        if row is not None:
            return str(row["publish_status"]) == WikiPublishStatus.PUBLISHED.value

        # Check attached federated public databases
        attached_dbs = {str(r["name"]) for r in conn.execute("PRAGMA database_list").fetchall()}
        for idx in range(min(len(self._structure.public_dirs), MAX_FEDERATED_DATABASES)):
            alias = f"pub_{idx}"
            if alias in attached_dbs:
                try:
                    c = conn.execute(
                        f"SELECT publish_status FROM {alias}.wiki_index_meta WHERE concept_name = ?",
                        (concept_name,),
                    )
                    r = c.fetchone()
                    if r is not None:
                        return str(r["publish_status"]) == WikiPublishStatus.PUBLISHED.value
                except sqlite3.DatabaseError:
                    continue
        return True

    def _filter_published(self, conn: sqlite3.Connection, results: list[tuple[str, float]]) -> list[tuple[str, float]]:
        return [(name, score) for name, score in results if self._is_published(conn, name)]

    def _query_fts(self, conn: sqlite3.Connection, fts_query: str, limit: int, offset: int) -> list[tuple[str, float]]:
        """Run the gated match over the primary index and every attached shared index; best match first.

        Fetches ``2 * limit`` rows from ``offset`` so the hybrid fusion has more candidates to rank.
        """
        fts_tables = attached_tables(conn, "wiki_fts")
        fts_union = " UNION ALL ".join(
            _published_match_select(conn, t, f"concept_name, rank, '{t}' AS src_tbl") for t in fts_tables
        )
        cursor = conn.execute(
            f"""
            SELECT concept_name, rank, src_tbl
            FROM ({fts_union})
            ORDER BY rank
            LIMIT ? OFFSET ?
            """,
            (*((fts_query,) * len(fts_tables)), limit * 2, offset),
        )
        results: list[tuple[str, float]] = []
        for row in cursor.fetchall():
            if self._is_sidecar_entry(str(row["concept_name"])):
                continue
            # The primary vault has decay 1.0; attached shared vaults get 0.9 so generic terms
            # cannot overtake the primary vault's own pages.
            decay = 0.9 if str(row["src_tbl"]).startswith("pub_") else 1.0
            results.append((row["concept_name"], relevance_from_rank(row["rank"]) * decay))
        return results

    async def search(self, query: str, limit: int = 5, offset: int = 0) -> list[tuple[str, float]]:
        """
        Search the index and return (concept_name, score).
        If Hybrid Search is enabled, performs FTS5 + Vector search and fuses via RRF.
        Returns a sorted list by score (higher is better).
        """
        safe_query = query.replace('"', "").replace("'", "").strip()
        if not safe_query:
            return []

        # 1. FTS5 Search
        fts_query = tokenize_for_fts(safe_query)

        def sync_fts_search() -> list[tuple[str, float]]:
            if not fts_query:
                return []
            with self._get_conn() as conn:
                try:
                    return self._query_fts(conn, fts_query, limit, offset)
                except sqlite3.ProgrammingError:
                    raise  # a query the code built wrongly is a bug to surface, not a damaged index to heal
                except sqlite3.DatabaseError as e:
                    logger.error(f"FTS search error: {e}")
                    if not fts5_auto_heal(conn, "wiki_fts"):
                        return []
                    logger.info("FTS5 auto-heal succeeded, retrying search")
                    with contextlib.suppress(sqlite3.DatabaseError):
                        return self._query_fts(conn, fts_query, limit, offset)
                    return []

        fts_results = await asyncio.to_thread(sync_fts_search)

        # 2. Vector Search (if enabled)
        vec_results: list[tuple[str, float]] = []
        if self._config.enable_hybrid_search and self._vector and self._embedding:
            await self._ensure_collection()
            try:
                query_vec = await self._embedding.embed(query)
                # Note: VectorStore search doesn't natively support offset, we slice the result
                search_limit = limit + offset
                search_res = await self._vector.search(
                    self._collection_name, query_vector=query_vec, limit=search_limit
                )
                for res in search_res[offset:]:
                    candidate = str(res.document.metadata.get("concept_name", res.document.id))
                    if self._is_sidecar_entry(candidate):
                        continue
                    vec_results.append((candidate, res.score))
            except EmbedInputTooLargeError:
                raise
            except Exception as e:
                logger.error(f"Wiki vector search failed: {e}")

        if vec_results:

            def sync_filter_vec(
                results: list[tuple[str, float]],
            ) -> list[tuple[str, float]]:
                # Vectors written under another spelling of a page count for that page once.
                pages = collapse_vector_hits([(self._index_key(name), score) for name, score in results])
                with self._get_conn() as conn:
                    return self._filter_published(conn, pages)

            vec_results = await asyncio.to_thread(sync_filter_vec, vec_results)

        # 3. Hybrid Fusion (RRF)
        if self._config.enable_hybrid_search and self._vector and self._embedding:
            if fts_results or vec_results:
                final_results = rrf_fusion([fts_results, vec_results], k=getattr(self._config, "rrf_k", 60))
            else:
                final_results = []
        else:
            final_results = fts_results

        # Sort and truncate
        final_results.sort(key=lambda x: x[1], reverse=True)
        return final_results[:limit]

    def get_truth(self, concept_name: str) -> str | None:
        """Get the cached truth content for context injection (published entries only)."""
        with self._get_conn() as conn:
            if not self._is_published(conn, concept_name):
                return None
            fts_tables = attached_tables(conn, "wiki_fts")
            fts_union = " UNION ALL ".join(f"SELECT truth_content FROM {t} WHERE concept_name = ?" for t in fts_tables)
            params = (concept_name,) * len(fts_tables)

            cursor = conn.execute(fts_union, params)
            row = cursor.fetchone()
            return row["truth_content"] if row else None


def _open_read_only(index_db: Path) -> AbstractContextManager[sqlite3.Connection]:
    """Open an index file read-only: no table is created and no schema is migrated; a missing file raises.

    A WAL index needs write access to its directory for the shared-memory file, so in a directory this process
    cannot write (a read-only volume) the file is opened immutable instead: nothing on this side can change it,
    and rows still in a ``-wal`` file are not seen. SQLite then assumes nobody changes the file, so a writer that
    keeps updating it makes reads fail or return inconsistent rows.
    """
    resolved = index_db.resolve()
    immutable = "" if os.access(resolved.parent, os.W_OK) else "&immutable=1"
    return contextlib.closing(sqlite3.connect(f"{resolved.as_uri()}?mode=ro{immutable}", uri=True))


def search_published_index(index_db: Path, fts_query: str, *, limit: int) -> list[tuple[str, str]]:
    """Return the ``limit`` best published pages of an index file as (concept_name, truth_content).

    For callers that read an index they do not own, such as a shared vault another process writes: the file is
    opened read-only, so no table is created and no schema is migrated (in a writable directory SQLite may leave
    its WAL side files next to the index). ``fts_query`` is FTS5 MATCH syntax. Raises ``sqlite3.Error`` when the
    file is missing or unreadable or the query is invalid.
    """
    with _open_read_only(index_db) as conn:
        select = _published_match_select(conn, "wiki_fts", "concept_name, truth_content")
        rows = conn.execute(f"{select} ORDER BY rank LIMIT ?", (fts_query, limit)).fetchall()
    return [(str(name or ""), str(truth or "")) for name, truth in rows]


def index_has_pages(index_db: Path) -> bool:
    """Whether an index file holds at least one concept page row; interim raw-text and sidecar rows do not count.

    ``search_published_index`` returns the same empty list for a question nothing matches and for an index that
    was created but never filled (any ``WikiIndexer`` creates its file on construction); this tells them apart.
    A draft or blocked page counts: the index was built for the vault. A raw upload waiting to be compiled does
    not: its pages are not indexed yet. Opened read-only like ``search_published_index``; raises ``sqlite3.Error``
    when the file is missing or unreadable.
    """
    with _open_read_only(index_db) as conn:
        row = conn.execute(f"SELECT 1 FROM wiki_fts WHERE {concept_rows_filter()} LIMIT 1").fetchone()
    return row is not None


WIKI_FTS_COLUMNS = ("concept_name", "truth_content", "search_terms")


def create_wiki_fts_table(conn: sqlite3.Connection, table: str = "wiki_fts") -> None:
    """Declare the wiki search table ``table`` unless it exists; ``table`` is a fixed internal name."""
    conn.execute(
        f'CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING fts5({", ".join(WIKI_FTS_COLUMNS)}, tokenize="{FTS_TOKENIZER}")'
    )


def migrate_wiki_fts_schema(conn: sqlite3.Connection) -> None:
    """Rebuild wiki_fts when it predates the ``search_terms`` column.

    FTS5 virtual tables cannot be altered in place and the index is a
    rebuildable cache, so legacy rows keep their existing search text in both
    columns while new upserts store the original truth plus segmented terms.
    """
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(wiki_fts)").fetchall()}
    if "search_terms" in columns:
        return

    logger.info("Migrating wiki_fts to the truth_content + search_terms schema")
    create_wiki_fts_table(conn, "wiki_fts_v2")
    conn.execute(
        "INSERT INTO wiki_fts_v2 (concept_name, truth_content, search_terms) "
        "SELECT concept_name, truth_content, truth_content FROM wiki_fts"
    )
    conn.execute("DROP TABLE wiki_fts")
    conn.execute("ALTER TABLE wiki_fts_v2 RENAME TO wiki_fts")
