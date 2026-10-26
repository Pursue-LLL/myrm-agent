"""Chat-row backed store of external CLI session ids.

[INPUT]
- myrm_agent_harness.toolkits.acp.types::CliSessionRecord (POS: ACP runtime type definitions)
- app.database.repositories.chat_cli_session_repo::ChatCliSessionRepository (POS: 外部 CLI Agent 会话记录仓储)
- app.database.factory::acquire_write_lock (POS: SQLite write lock for a transaction that reads before it writes)
- app.platform_utils::get_session_factory (POS: database sessions)

[OUTPUT]
- ChatCliSessionStore: harness ``CliSessionStore`` persisting one chat's external CLI sessions on the chat row

[POS]
Server half of external-agent session continuity. The harness decides when to remember and persist a
CLI session id; this store only gives those ids a durable home, so a restart of the server resumes the same
external conversation. A record is never deleted, the next session the CLI announces overwrites it. Failures
propagate: the harness logs them and the turn carries on.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.acp.types import CliSessionRecord

from app.database.factory import acquire_write_lock
from app.database.repositories.chat_cli_session_repo import ChatCliSessionRepository
from app.platform_utils import get_session_factory


class ChatCliSessionStore:
    """The external CLI sessions of one chat, kept on the chat row."""

    def __init__(self, chat_id: str) -> None:
        self._chat_id = chat_id

    async def load(self, session_id: str) -> CliSessionRecord | None:
        async with get_session_factory()() as db:
            entry = await ChatCliSessionRepository.get(db, self._chat_id, session_id)
        if not entry:
            return None
        cli_session_id, cwd = entry.get("cli_session_id"), entry.get("cwd")
        if not isinstance(cli_session_id, str) or not cli_session_id or not isinstance(cwd, str):
            return None
        return CliSessionRecord(cli_session_id, cwd)

    async def save(self, session_id: str, record: CliSessionRecord) -> None:
        entry = {"cli_session_id": record.cli_session_id, "cwd": record.cwd}
        async with get_session_factory()() as db:
            await acquire_write_lock(db)
            await ChatCliSessionRepository.put(db, self._chat_id, session_id, entry)
            await db.commit()
