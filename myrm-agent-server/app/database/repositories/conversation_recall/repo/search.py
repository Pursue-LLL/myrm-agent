"""[INPUT]
- app.database.repositories.conversation_recall.sql / .types (POS: SQL + row types)

[OUTPUT]
- SearchMixin

[POS]
ConversationRecallRepository mixin: FTS5 search with degraded/fault recovery, document listing and row de-duplication.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall.sql import (
    filter_sql,
)
from app.database.repositories.conversation_recall.types import (
    ConversationRecallDocumentRow,
    ConversationRecallRow,
    recall_document_row,
    recall_row,
)

logger = logging.getLogger("app.database.repositories.conversation_recall.repo")


class SearchMixin:
    @staticmethod
    async def search(
        db: AsyncSession,
        *,
        safe_query: str,
        limit: int,
        current_chat_id: str | None,
        agent_id: str | None,
        current_source: str | None,
        scope: str,
        lineage_chat_ids: list[str],
        since: datetime | None,
        until: datetime | None,
    ) -> list[ConversationRecallRow]:
        filters, params = filter_sql(
            current_chat_id=current_chat_id,
            agent_id=agent_id,
            current_source=current_source,
            scope=scope,
            lineage_chat_ids=lineage_chat_ids,
            since=since,
            until=until,
        )
        params.update({"query": safe_query, "limit": limit})
        segment_rows = []
        try:
            segment_rows = (
                (
                    await db.execute(
                        text(f"""
                        SELECT
                            d.chat_id AS chat_id,
                            d.title AS title,
                            d.agent_id AS agent_id,
                            d.source AS source,
                            s.message_id AS message_id,
                            snippet(conversation_recall_segments_fts, 0, '<mark>', '</mark>', '...', 56) AS snippet,
                            d.summary AS summary,
                            s.sent_at AS last_message_at,
                            d.created_at AS created_at,
                            d.updated_at AS updated_at,
                            conversation_recall_segments_fts.rank AS rank,
                            f.parent_chat_id AS fork_parent_id
                        FROM conversation_recall_segments_fts
                        JOIN conversation_recall_segments s ON s.id = conversation_recall_segments_fts.rowid
                        JOIN conversation_recall_documents d ON d.chat_id = s.chat_id
                        LEFT JOIN conversation_forks f ON f.child_chat_id = d.chat_id
                        WHERE conversation_recall_segments_fts MATCH :query
                          AND d.is_excluded = 0
                          {filters}
                        ORDER BY conversation_recall_segments_fts.rank ASC, s.sent_at DESC, d.last_message_at DESC
                        LIMIT :limit
                    """),
                        params,
                    )
                )
                .mappings()
                .all()
            )
        except Exception as exc:
            logger.warning("conversation_recall_segments_fts MATCH failed (degraded/rebuilding): %s", exc)
            try:
                await db.execute(
                    text("INSERT INTO conversation_recall_segments_fts(conversation_recall_segments_fts) VALUES('rebuild')")
                )
                logger.info("Auto-rebuilt conversation_recall_segments_fts successfully")
            except Exception:
                pass

        document_rows = []
        try:
            document_rows = (
                (
                    await db.execute(
                        text(f"""
                        SELECT
                            d.chat_id AS chat_id,
                            d.title AS title,
                            d.agent_id AS agent_id,
                            d.source AS source,
                            d.last_message_id AS message_id,
                            snippet(conversation_recall_fts, -1, '<mark>', '</mark>', '...', 56) AS snippet,
                            d.summary AS summary,
                            d.last_message_at AS last_message_at,
                            d.created_at AS created_at,
                            d.updated_at AS updated_at,
                            conversation_recall_fts.rank AS rank,
                            f.parent_chat_id AS fork_parent_id
                        FROM conversation_recall_fts
                        JOIN conversation_recall_documents d ON d.id = conversation_recall_fts.rowid
                        LEFT JOIN conversation_forks f ON f.child_chat_id = d.chat_id
                        WHERE conversation_recall_fts MATCH :query
                          AND d.is_excluded = 0
                          {filters}
                        ORDER BY conversation_recall_fts.rank ASC, d.last_message_at DESC, d.updated_at DESC
                        LIMIT :limit
                    """),
                        params,
                    )
                )
                .mappings()
                .all()
            )
        except Exception as exc:
            logger.warning("conversation_recall_fts MATCH failed (degraded/rebuilding): %s", exc)
            try:
                await db.execute(text("INSERT INTO conversation_recall_fts(conversation_recall_fts) VALUES('rebuild')"))
                logger.info("Auto-rebuilt conversation_recall_fts successfully")
            except Exception:
                pass

        results = _dedupe_recall_rows(
            [recall_row(row) for row in [*segment_rows, *document_rows]],
            limit=limit,
        )
        if results:
            return results

        # Two-tier fallback for short keywords (< 3 chars) or CJK where trigram yields 0 hits
        fallback_rows = []
        try:
            fallback_params = {**params, "kw_pattern": f"%{safe_query}%"}
            fallback_rows = (
                (
                    await db.execute(
                        text(f"""
                        SELECT
                            d.chat_id AS chat_id,
                            d.title AS title,
                            d.agent_id AS agent_id,
                            d.source AS source,
                            s.message_id AS message_id,
                            SUBSTR(s.segment_text, 1, 100) AS snippet,
                            d.summary AS summary,
                            s.sent_at AS last_message_at,
                            d.created_at AS created_at,
                            d.updated_at AS updated_at,
                            -1.0 AS rank,
                            f.parent_chat_id AS fork_parent_id
                        FROM conversation_recall_segments s
                        JOIN conversation_recall_documents d ON d.chat_id = s.chat_id
                        LEFT JOIN conversation_forks f ON f.child_chat_id = d.chat_id
                        WHERE (s.segment_text LIKE :kw_pattern OR d.searchable_text LIKE :kw_pattern)
                          AND d.is_excluded = 0
                          {filters}
                        ORDER BY s.sent_at DESC, d.last_message_at DESC
                        LIMIT :limit
                    """),
                        fallback_params,
                    )
                )
                .mappings()
                .all()
            )
        except Exception as fb_exc:
            logger.warning("conversation_recall fallback LIKE search failed: %s", fb_exc)

        return _dedupe_recall_rows(
            [recall_row(row) for row in fallback_rows],
            limit=limit,
        )

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        *,
        excluded: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ConversationRecallDocumentRow], int]:
        filters = ""
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if excluded is not None:
            filters = "WHERE is_excluded = :is_excluded"
            params["is_excluded"] = 1 if excluded else 0

        total = (
            await db.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM conversation_recall_documents
                    {filters}
                """),
                params,
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    text(f"""
                    SELECT
                        chat_id,
                        title,
                        agent_id,
                        source,
                        snippet,
                        summary,
                        last_message_at,
                        created_at,
                        updated_at,
                        is_excluded
                    FROM conversation_recall_documents
                    {filters}
                    ORDER BY is_excluded DESC, last_message_at DESC, updated_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return [recall_document_row(row) for row in rows], int(total or 0)


def _dedupe_recall_rows(rows: list[ConversationRecallRow], *, limit: int) -> list[ConversationRecallRow]:
    ordered = sorted(rows, key=lambda row: (row.rank, -_datetime_sort_value(row.last_message_at)))
    deduped: list[ConversationRecallRow] = []
    seen_chat_ids: set[str] = set()
    for row in ordered:
        if row.chat_id in seen_chat_ids:
            continue
        seen_chat_ids.add(row.chat_id)
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return deduped


def _datetime_sort_value(value: datetime | None) -> float:
    if value is None:
        return 0.0
    return value.timestamp()
