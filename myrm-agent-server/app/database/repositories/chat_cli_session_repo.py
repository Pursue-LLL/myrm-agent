"""Chat external CLI session repository.

[INPUT]
app.database.models::Chat (POS: 会话与消息域模型。管理聊天会话、消息记录和对话分支)
sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
CliSessionEntry: one stored external CLI session, ``{"cli_session_id": ..., "cwd": ...}``.
ChatCliSessionRepository: read and write the external CLI session entries of a chat.

[POS]
外部 CLI Agent 会话记录仓储。读写 Chat.external_cli_sessions（harness session id → CLI 原生会话 id 与创建它的目录），
写入口跳过不存在的会话与无痕会话，且不触碰 `updated_at`：续接记录是记账，不是会话活动。
"""

from __future__ import annotations

from typing import TypeAlias

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat

CliSessionEntry: TypeAlias = dict[str, str]


def _sessions_of(value: object) -> dict[str, object]:
    """The stored column as a mapping; anything else (a JSON ``null``, a corrupt value) holds no sessions."""
    return dict(value) if isinstance(value, dict) else {}


class ChatCliSessionRepository:
    """Reads and writes the CLI-native session ids an external agent resumes a chat's conversation with.

    ``put`` reads before it writes: the caller holds the SQLite write lock for the transaction
    (``acquire_write_lock``) so two writers cannot overwrite each other's entry.
    """

    @staticmethod
    async def get(db: AsyncSession, chat_id: str, session_id: str) -> CliSessionEntry | None:
        """Return the stored entry of ``session_id``, or ``None`` when the chat or the entry does not exist."""
        stored = (await db.execute(select(Chat.external_cli_sessions).where(Chat.id == chat_id))).scalar_one_or_none()
        entry = _sessions_of(stored).get(session_id)
        return entry if isinstance(entry, dict) else None

    @staticmethod
    async def put(db: AsyncSession, chat_id: str, session_id: str, entry: CliSessionEntry) -> None:
        """Store ``entry``; a missing chat and an incognito chat (which keeps nothing) are left untouched."""
        row = (await db.execute(select(Chat.is_incognito, Chat.external_cli_sessions).where(Chat.id == chat_id))).one_or_none()
        if row is None or row.is_incognito:
            return
        sessions = {**_sessions_of(row.external_cli_sessions), session_id: entry}
        await db.execute(
            update(Chat).where(Chat.id == chat_id).values(external_cli_sessions=sessions, updated_at=Chat.updated_at)
        )
