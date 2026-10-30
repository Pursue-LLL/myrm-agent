"""Wiki index read operations (SQLite FTS5 + Qdrant hybrid search).

[INPUT]
- sqlite3 (POS: standard library database)
- myrm_agent_harness.toolkits.retriever.embedding.window_policy::EmbedInputTooLargeError (POS: embedding input window violation)
- myrm_agent_harness.toolkits.retriever.fusion_strategies::rrf_fusion (POS: result fusion strategy)
- myrm_agent_harness.utils.db.fts5::fts5_auto_heal (POS: FTS5 corruption auto-heal helper)
- ..core.config::WikiConfig (POS: wiki configuration center)
- ..core.frontmatter_contract::WikiPublishStatus (POS: publish_status SSOT)
- .sidecar_index::_SIDECAR_PREFIX (POS: L0/L1 sidecar index operations)
- .tokenizer::tokenize_for_fts (POS: FTS5 query tokenizer)
- .vector_chunks::collapse_vector_hits (POS: L2 chunk vector hit collapsing)

[OUTPUT]
- FtsSearchMixin: FTS5 + vector search/get_truth with the publish_status gate for WikiIndexer; vector hits under another spelling collapse onto the page key
- search_published_index: read-only top published pages of an index file the caller does not own
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
import sqlite3
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.retriever.embedding.window_policy import (
    EmbedInputTooLargeError,
)
from myrm_agent_harness.toolkits.retriever.fusion_strategies import rrf_fusion
from myrm_agent_harness.utils.db.fts5 import fts5_auto_heal

from ..core.config import WikiConfig
from ..core.frontmatter_contract import WikiPublishStatus
from .sidecar_index import _SIDECAR_PREFIX
from .tokenizer import tokenize_for_fts
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
        for idx in range(min(len(self._structure.public_dirs), 6)):
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
                except (sqlite3.OperationalError, sqlite3.DatabaseError):
                    continue
        return True

    def _filter_published(self, conn: sqlite3.Connection, results: list[tuple[str, float]]) -> list[tuple[str, float]]:
        return [(name, score) for name, score in results if self._is_published(conn, name)]

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
        fts_results: list[tuple[str, float]] = []

        def sync_fts_search() -> list[tuple[str, float]]:
            results = []
            with self._get_conn() as conn:
                try:
                    fts_tables = ["wiki_fts"]
                    attached_dbs = {str(row["name"]) for row in conn.execute("PRAGMA database_list").fetchall()}
                    for idx in range(min(len(self._structure.public_dirs), 6)):
                        alias = f"pub_{idx}"
                        if alias in attached_dbs:
                            try:
                                has_table = conn.execute(
                                    f"SELECT 1 FROM {alias}.sqlite_master WHERE type IN ('table', 'view') AND name = 'wiki_fts'"
                                ).fetchone()
                                if has_table:
                                    fts_tables.append(f"{alias}.wiki_fts")
                            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                                continue

                    fts_query = tokenize_for_fts(safe_query)

                    if fts_query:
                        # In SQLite FTS5, the MATCH operator can be used on the table name.
                        # e.g., pub_0.wiki_fts MATCH ? is valid, but the column name inside WHERE is wiki_fts MATCH ?
                        fts_union = " UNION ALL ".join(
                            _published_match_select(conn, t, f"concept_name, rank, '{t}' AS src_tbl")
                            for t in fts_tables
                        )
                        params = (fts_query,) * len(fts_tables)

                        cursor = conn.execute(
                            f"""
                            SELECT concept_name, rank, src_tbl
                            FROM ({fts_union})
                            ORDER BY rank
                            LIMIT ? OFFSET ?
                            """,
                            (*params, limit * 2, offset),  # Fetch more for fusion
                        )

                        for row in cursor.fetchall():
                            if self._is_sidecar_entry(str(row["concept_name"])):
                                continue
                            # FTS5 rank is negative, lower is better. We invert it for RRF fusion.
                            # Primary vault has decay=1.0; attached federated public vaults receive 0.9 to prevent generic terms from overtaking primary truths.
                            decay = 0.9 if str(row["src_tbl"]).startswith("pub_") else 1.0
                            score = (1.0 / (abs(row["rank"]) + 1.0)) * decay
                            results.append((row["concept_name"], score))
                except sqlite3.OperationalError as e:
                    logger.error(f"FTS search error: {e}")
                    healed = fts5_auto_heal(conn, "wiki_fts")
                    if healed and fts_query:
                        logger.info("FTS5 auto-heal succeeded, retrying search")
                        with contextlib.suppress(sqlite3.OperationalError):
                            cursor = conn.execute(
                                f"""
                                SELECT concept_name, rank, src_tbl
                                FROM ({fts_union})
                                ORDER BY rank
                                LIMIT ? OFFSET ?
                                """,
                                (*params, limit * 2, offset),
                            )
                            for row in cursor.fetchall():
                                if self._is_sidecar_entry(str(row["concept_name"])):
                                    continue
                                decay = 0.9 if str(row["src_tbl"]).startswith("pub_") else 1.0
                                score = (1.0 / (abs(row["rank"]) + 1.0)) * decay
                                results.append((row["concept_name"], score))
            return results

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
            fts_tables = ["wiki_fts"]
            attached_dbs = {str(row["name"]) for row in conn.execute("PRAGMA database_list").fetchall()}
            for idx in range(min(len(self._structure.public_dirs), 6)):
                alias = f"pub_{idx}"
                if alias in attached_dbs:
                    try:
                        has_table = conn.execute(
                            f"SELECT 1 FROM {alias}.sqlite_master WHERE type IN ('table', 'view') AND name = 'wiki_fts'"
                        ).fetchone()
                        if has_table:
                            fts_tables.append(f"{alias}.wiki_fts")
                    except (sqlite3.OperationalError, sqlite3.DatabaseError):
                        continue

            fts_union = " UNION ALL ".join(f"SELECT truth_content FROM {t} WHERE concept_name = ?" for t in fts_tables)
            params = (concept_name,) * len(fts_tables)

            cursor = conn.execute(fts_union, params)
            row = cursor.fetchone()
            return row["truth_content"] if row else None


def search_published_index(index_db: Path, fts_query: str, *, limit: int) -> list[tuple[str, str]]:
    """Return the ``limit`` best published pages of an index file as (concept_name, truth_content).

    For callers that read an index they do not own, such as a shared vault another process writes: the file is
    opened read-only and nothing is migrated or created. ``fts_query`` is FTS5 MATCH syntax. Raises
    ``sqlite3.Error`` when the file is missing or unreadable or the query is invalid.
    """
    with contextlib.closing(sqlite3.connect(f"{index_db.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        select = _published_match_select(conn, "wiki_fts", "concept_name, truth_content")
        rows = conn.execute(f"{select} ORDER BY rank LIMIT ?", (fts_query, limit)).fetchall()
    return [(str(name or ""), str(truth or "")) for name, truth in rows]


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
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts_v2 USING fts5(
            concept_name,
            truth_content,
            search_terms,
            tokenize="unicode61 remove_diacritics 1"
        )
    """
    )
    conn.execute(
        "INSERT INTO wiki_fts_v2 (concept_name, truth_content, search_terms) "
        "SELECT concept_name, truth_content, truth_content FROM wiki_fts"
    )
    conn.execute("DROP TABLE wiki_fts")
    conn.execute("ALTER TABLE wiki_fts_v2 RENAME TO wiki_fts")
