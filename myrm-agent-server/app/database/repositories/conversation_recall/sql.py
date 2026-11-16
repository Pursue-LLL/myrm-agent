"""Conversation recall raw SQLite statements.

[INPUT]
- SQLite FTS5 (POS: embedded full-text search index)

[OUTPUT]
- CONVERSATION_RECALL_SCHEMA_SQL: Schema and trigger statements for the recall index.
- CONVERSATION_RECALL_BOOTSTRAP_SQL: Backfill statement for missing recall documents.
- CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL: Backfill statement for missing recall segments.
- UPSERT_REBUILD_SQL: Rebuild one chat document from canonical chat/message rows.
- UPSERT_SEGMENT_SQL: Upsert one message segment from the incremental write path.
- visible_document_sql: The condition a recall document meets before the model may read it.
- filter_sql: Build the parameterized conditions of a recall read: visibility first, then scope, lineage and time.
- HIGHLIGHT_OPEN, HIGHLIGHT_CLOSE: Markers FTS5 puts around a matched term in a snippet.

[POS]
Conversation Recall SQL 契约层。集中定义 SQLite/FTS5 DDL、回填语句、可见性条件、参数化过滤片段和 snippet 高亮标记。
"""

from __future__ import annotations

from datetime import datetime

# The markers FTS5 puts around a matched term in a snippet. They are Unicode noncharacters, which ordinary chat text does
# not hold, so a marker is never taken for text a person typed: ``<mark>`` is not safe for that, anyone can write it.
HIGHLIGHT_OPEN = "\ufdd0"
HIGHLIGHT_CLOSE = "\ufdd1"

CONVERSATION_RECALL_SCHEMA_SQL: list[str] = [
    """CREATE TABLE IF NOT EXISTS conversation_recall_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id VARCHAR(255) NOT NULL UNIQUE REFERENCES chats(id) ON DELETE CASCADE,
        agent_id VARCHAR(255),
        source VARCHAR(50) NOT NULL DEFAULT 'web',
        title VARCHAR(500),
        summary TEXT,
        snippet TEXT NOT NULL DEFAULT '',
        searchable_text TEXT NOT NULL DEFAULT '',
        last_message_id VARCHAR(255),
        last_message_at TIMESTAMP,
        is_excluded BOOLEAN NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_chat ON conversation_recall_documents(chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_agent ON conversation_recall_documents(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_source ON conversation_recall_documents(source)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_updated ON conversation_recall_documents(updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_excluded ON conversation_recall_documents(is_excluded)",
    """CREATE VIRTUAL TABLE IF NOT EXISTS conversation_recall_fts USING fts5(
        title,
        summary,
        snippet,
        searchable_text,
        content=conversation_recall_documents,
        content_rowid=id,
        tokenize='trigram'
    )""",
    """CREATE TRIGGER IF NOT EXISTS conversation_recall_fts_insert
        AFTER INSERT ON conversation_recall_documents BEGIN
        INSERT INTO conversation_recall_fts(rowid, title, summary, snippet, searchable_text)
        VALUES (new.id, new.title, new.summary, new.snippet, new.searchable_text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS conversation_recall_fts_delete
        AFTER DELETE ON conversation_recall_documents BEGIN
        INSERT INTO conversation_recall_fts(conversation_recall_fts, rowid, title, summary, snippet, searchable_text)
        VALUES('delete', old.id, old.title, old.summary, old.snippet, old.searchable_text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS conversation_recall_fts_update
        AFTER UPDATE ON conversation_recall_documents BEGIN
        INSERT INTO conversation_recall_fts(conversation_recall_fts, rowid, title, summary, snippet, searchable_text)
        VALUES('delete', old.id, old.title, old.summary, old.snippet, old.searchable_text);
        INSERT INTO conversation_recall_fts(rowid, title, summary, snippet, searchable_text)
        VALUES (new.id, new.title, new.summary, new.snippet, new.searchable_text);
    END""",
    """CREATE TABLE IF NOT EXISTS conversation_recall_segments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id VARCHAR(255) NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        message_id VARCHAR(255) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        segment_ordinal INTEGER NOT NULL DEFAULT 0,
        role VARCHAR(20) NOT NULL,
        segment_text TEXT NOT NULL DEFAULT '',
        sent_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chat_id, message_id, segment_ordinal)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_segments_chat ON conversation_recall_segments(chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_segments_message ON conversation_recall_segments(message_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_recall_segments_sent ON conversation_recall_segments(sent_at DESC)",
    """CREATE VIRTUAL TABLE IF NOT EXISTS conversation_recall_segments_fts USING fts5(
        segment_text,
        content=conversation_recall_segments,
        content_rowid=id,
        tokenize='trigram'
    )""",
    """CREATE TRIGGER IF NOT EXISTS conversation_recall_segments_fts_insert
        AFTER INSERT ON conversation_recall_segments BEGIN
        INSERT INTO conversation_recall_segments_fts(rowid, segment_text)
        VALUES (new.id, new.segment_text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS conversation_recall_segments_fts_delete
        AFTER DELETE ON conversation_recall_segments BEGIN
        INSERT INTO conversation_recall_segments_fts(conversation_recall_segments_fts, rowid, segment_text)
        VALUES('delete', old.id, old.segment_text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS conversation_recall_segments_fts_update
        AFTER UPDATE ON conversation_recall_segments BEGIN
        INSERT INTO conversation_recall_segments_fts(conversation_recall_segments_fts, rowid, segment_text)
        VALUES('delete', old.id, old.segment_text);
        INSERT INTO conversation_recall_segments_fts(rowid, segment_text)
        VALUES (new.id, new.segment_text);
    END""",
]

_REBUILD_SELECT_SQL = """
    SELECT
        c.id AS chat_id,
        c.agent_id AS agent_id,
        c.source AS source,
        c.title AS title,
        c.compacted_summary AS summary,
        COALESCE(
            (
                SELECT m.content
                FROM messages m
                WHERE m.chat_id = c.id AND m.is_active = 1
                ORDER BY m.sent_at DESC, m.created_at DESC
                LIMIT 1
            ),
            c.last_message,
            c.first_message,
            ''
        ) AS snippet,
        COALESCE(
            (
                SELECT group_concat(line, char(10))
                FROM (
                    SELECT m.role || ': ' || m.content AS line
                    FROM messages m
                    WHERE m.chat_id = c.id AND m.is_active = 1
                    ORDER BY m.sent_at ASC, m.created_at ASC
                )
            ),
            ''
        ) AS searchable_text,
        (
            SELECT m.id
            FROM messages m
            WHERE m.chat_id = c.id AND m.is_active = 1
            ORDER BY m.sent_at DESC, m.created_at DESC
            LIMIT 1
        ) AS last_message_id,
        (
            SELECT m.sent_at
            FROM messages m
            WHERE m.chat_id = c.id AND m.is_active = 1
            ORDER BY m.sent_at DESC, m.created_at DESC
            LIMIT 1
        ) AS last_message_at,
        c.created_at AS created_at,
        c.updated_at AS updated_at
    FROM chats c
"""

UPSERT_REBUILD_SQL = f"""
    INSERT INTO conversation_recall_documents (
        chat_id,
        agent_id,
        source,
        title,
        summary,
        snippet,
        searchable_text,
        last_message_id,
        last_message_at,
        created_at,
        updated_at
    )
    {_REBUILD_SELECT_SQL}
    WHERE c.id = :chat_id
    ON CONFLICT(chat_id) DO UPDATE SET
        agent_id = excluded.agent_id,
        source = excluded.source,
        title = excluded.title,
        summary = excluded.summary,
        snippet = excluded.snippet,
        searchable_text = excluded.searchable_text,
        last_message_id = excluded.last_message_id,
        last_message_at = excluded.last_message_at,
        updated_at = CURRENT_TIMESTAMP
"""

CONVERSATION_RECALL_BOOTSTRAP_SQL = f"""
    INSERT INTO conversation_recall_documents (
        chat_id,
        agent_id,
        source,
        title,
        summary,
        snippet,
        searchable_text,
        last_message_id,
        last_message_at,
        created_at,
        updated_at
    )
    {_REBUILD_SELECT_SQL}
    WHERE NOT EXISTS (
        SELECT 1
        FROM conversation_recall_documents d
        WHERE d.chat_id = c.id
    )
"""

UPSERT_SEGMENTS_FOR_CHAT_SQL = """
    INSERT INTO conversation_recall_segments (
        chat_id,
        message_id,
        segment_ordinal,
        role,
        segment_text,
        sent_at,
        created_at,
        updated_at
    )
    SELECT
        m.chat_id,
        m.id,
        0,
        m.role,
        m.content,
        m.sent_at,
        m.created_at,
        CURRENT_TIMESTAMP
    FROM messages m
    WHERE m.chat_id = :chat_id
      AND m.is_active = 1
    ON CONFLICT(chat_id, message_id, segment_ordinal) DO UPDATE SET
        role = excluded.role,
        segment_text = excluded.segment_text,
        sent_at = excluded.sent_at,
        updated_at = CURRENT_TIMESTAMP
"""

UPSERT_SEGMENT_SQL = """
    INSERT INTO conversation_recall_segments (
        chat_id,
        message_id,
        segment_ordinal,
        role,
        segment_text,
        sent_at,
        created_at,
        updated_at
    )
    VALUES (
        :chat_id,
        :message_id,
        0,
        :role,
        :content,
        :sent_at,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
    ON CONFLICT(chat_id, message_id, segment_ordinal) DO UPDATE SET
        role = excluded.role,
        segment_text = excluded.segment_text,
        sent_at = excluded.sent_at,
        updated_at = CURRENT_TIMESTAMP
"""

DELETE_SEGMENTS_FOR_CHAT_SQL = """
    DELETE FROM conversation_recall_segments
    WHERE chat_id = :chat_id
"""

CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL = """
    INSERT INTO conversation_recall_segments (
        chat_id,
        message_id,
        segment_ordinal,
        role,
        segment_text,
        sent_at,
        created_at,
        updated_at
    )
    SELECT
        m.chat_id,
        m.id,
        0,
        m.role,
        m.content,
        m.sent_at,
        m.created_at,
        CURRENT_TIMESTAMP
    FROM messages m
    WHERE m.is_active = 1
      AND NOT EXISTS (
          SELECT 1
          FROM conversation_recall_segments s
          WHERE s.chat_id = m.chat_id
            AND s.message_id = m.id
            AND s.segment_ordinal = 0
      )
"""


def visible_document_sql(alias: str) -> str:
    """The condition a recall document meets before the model may read it, for the table aliased ``alias``.

    The user has not excluded it, and it is not a web incognito chat: those are promised to vanish once idle, so no
    other chat may read them meanwhile. A transcript import carries the incognito flag only to stay out of the sidebar,
    so it stays readable. The incognito flag can change after a chat was indexed, so it is read from ``chats`` when the
    query runs, not copied into the index.
    """
    return (
        f"{alias}.is_excluded = 0 AND NOT EXISTS ("
        f"SELECT 1 FROM chats pc WHERE pc.id = {alias}.chat_id AND pc.is_incognito = 1 AND pc.source = 'web')"
    )


def filter_sql(
    *,
    current_chat_id: str | None,
    agent_id: str | None,
    current_source: str | None,
    scope: str,
    lineage_chat_ids: list[str],
    since: datetime | None,
    until: datetime | None,
) -> tuple[str, dict[str, object]]:
    """The conditions a read of the recall documents (alias ``d``) applies, joined by ``AND`` and never empty.

    Visibility always comes first and no argument turns it off, so a read that builds its filters here cannot return a
    document the model may not see. The caller puts the string after ``WHERE`` or after another condition and ``AND``.
    """
    clauses: list[str] = [visible_document_sql("d")]
    params: dict[str, object] = {}
    if current_chat_id:
        clauses.append("d.chat_id != :current_chat_id")
        params["current_chat_id"] = current_chat_id
    if scope in {"current_agent", "agent_and_source"}:
        if agent_id is None:
            clauses.append("d.agent_id IS NULL")
        else:
            clauses.append("d.agent_id = :agent_id")
            params["agent_id"] = agent_id
    if scope in {"same_source", "agent_and_source"} and current_source:
        clauses.append("d.source = :current_source")
        params["current_source"] = current_source
    if lineage_chat_ids:
        placeholders: list[str] = []
        for index, chat_id in enumerate(lineage_chat_ids):
            key = f"lineage_chat_{index}"
            placeholders.append(f":{key}")
            params[key] = chat_id
        clauses.append(f"d.chat_id IN ({', '.join(placeholders)})")
    if since is not None:
        clauses.append("d.last_message_at >= :since")
        params["since"] = since
    if until is not None:
        clauses.append("d.last_message_at <= :until")
        params["until"] = until
    return "\n                      AND ".join(clauses), params
