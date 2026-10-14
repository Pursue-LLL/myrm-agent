"""Safe Vault Purge and Cascade Synchronization Service.

[INPUT]
- app.database.connection::get_database_engine, get_session_factory (POS: database engine and session factory of the active deployment mode)
- myrm_agent_harness.api::safe_purge_fts5_virtual_table (POS: FTS5 purge that leaves no shadow-table orphan rows)
- app.services.chat.chat_disposal::clear_conversation_state, clear_runtime_caches, remove_chat_files (POS: single definition of the per-chat teardown steps)
- app.services.agent.gateway::get_agent_gateway (POS: which conversations have a turn in flight)

[OUTPUT]
- SafeVaultPurgeResult: Structured audit summary of purged entities and preserved settings
- VaultPurgeBusyError: raised when a conversation is mid-turn, before anything is touched
- SafeVaultPurgeService: Transactional inverse purge orchestrator with whitelist protection

[POS]
System-level safe vault purge orchestrator. Executes reverse-dependency physical wipes of
conversation corpora, the state and files of every chat, FTS5 shadow indexes, and consumer
cursors while strictly safeguarding user configuration (API Keys, providers, custom agents,
and channel pairing identities).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text

from app.database.connection import get_database_engine
from app.services.agent.gateway import get_agent_gateway
from app.services.chat import chat_disposal

logger = logging.getLogger(__name__)

# Global concurrency guard: ensures only one vault purge or conflicting write runs at once
_PURGE_LOCK = asyncio.Lock()


class VaultPurgeBusyError(RuntimeError):
    """A conversation is mid-turn; wiping beneath it would race the turn's own writes."""

    def __init__(self, running: int) -> None:
        super().__init__(f"Cannot purge while {running} conversations are running; stop them or wait, then retry")
        self.running = running


@dataclass
class SafeVaultPurgeResult:
    """Audit summary of entities wiped and settings preserved during safe vault purge."""

    success: bool
    purged_chats: int = 0
    purged_messages: int = 0
    purged_channel_messages: int = 0
    purged_memory_events: int = 0
    checkpoint_cleared_chats: int = 0
    cleared_sandboxes: int = 0
    fts_tables_purged: list[str] = field(default_factory=list)
    cursors_reset: list[str] = field(default_factory=list)
    preserved_agents: int = 0
    preserved_api_keys: int = 0
    preserved_user_configs: int = 0
    preserved_channel_pairings: int = 0
    duration_ms: float = 0.0
    error: str | None = None


class SafeVaultPurgeService:
    """Orchestrates cascade-proof, reverse-dependency data purge with whitelist protection."""

    # FTS5 virtual tables subject to explicit reverse wipe
    FTS_VIRTUAL_TABLES: tuple[str, ...] = (
        "conversation_recall_segments_fts",
        "conversation_recall_fts",
        "messages_fts",
    )

    # Memory pipeline queues and event log emptied together with the conversations they were derived from
    MEMORY_PIPELINE_TABLES: tuple[str, ...] = (
        "pending_memories",
        "memory_extract_retries",
        "memory_operation_events",
    )

    @classmethod
    async def purge_vault(
        cls,
        *,
        purge_memories: bool = True,
        purge_sandboxes: bool = True,
        reclaim_disk: bool = True,
    ) -> SafeVaultPurgeResult:
        """Execute atomic safe vault purge with strict whitelist preservation.

        Order of operations (strict inverse topology):
        1. Acquire PurgeLock to block concurrent pipeline writers, and refuse (``VaultPurgeBusyError``)
           while any conversation has a turn in flight.
        2. Clean FTS5 shadow structures before source rows are touched.
        3. Stop the runtime work of every chat and drop its checkpoint threads and session grants while
           the chat rows still exist, so an interrupted purge never strands state whose chat can no
           longer be listed.
        4. Delete conversation recall, chat messages, and channel messages in one transaction.
        5. In the same transaction, empty the memory pipeline tables (when ``purge_memories``)
           and reset sqlite_sequence counters / consumer cursors.
        6. Remove the sandbox worktrees, workspaces and artifacts of the purged chats.
        7. Run PRAGMA incremental_vacuum and optimize to reclaim physical disk space.
        """
        async with _PURGE_LOCK:
            running = get_agent_gateway().active_session_ids()
            if running:
                raise VaultPurgeBusyError(len(running))

            start_time = datetime.now(UTC)
            engine = get_database_engine()
            result = SafeVaultPurgeResult(success=False)

            try:
                # Phase 1: Query existing tables & count preserved assets (whitelist proof)
                existing_tables: set[str] = set()
                async with engine.connect() as conn:
                    table_rows = (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).fetchall()
                    existing_tables = {r[0] for r in table_rows}

                    if "agents" in existing_tables:
                        result.preserved_agents = await conn.scalar(text("SELECT COUNT(*) FROM agents")) or 0
                    if "api_keys" in existing_tables:
                        result.preserved_api_keys = await conn.scalar(text("SELECT COUNT(*) FROM api_keys")) or 0
                    if "user_configs" in existing_tables:
                        result.preserved_user_configs = await conn.scalar(text("SELECT COUNT(*) FROM user_configs")) or 0
                    if "channel_pairings" in existing_tables:
                        result.preserved_channel_pairings = await conn.scalar(text("SELECT COUNT(*) FROM channel_pairings")) or 0

                # Phase 2: Reverse-clean FTS5 virtual tables
                # Execute asynchronously via AsyncConnection to eliminate driver-level coroutine mismatch
                async with engine.begin() as conn:
                    for fts_tbl in cls.FTS_VIRTUAL_TABLES:
                        if fts_tbl in existing_tables:
                            try:
                                await conn.execute(text(f"INSERT INTO {fts_tbl}({fts_tbl}) VALUES('delete-all')"))
                            except Exception:
                                try:
                                    await conn.execute(text(f"DELETE FROM {fts_tbl}"))
                                except Exception as exc:
                                    logger.warning(
                                        "FTS5 direct delete failed for %s: %s",
                                        fts_tbl,
                                        exc,
                                    )
                            try:
                                await conn.execute(text(f"INSERT INTO {fts_tbl}({fts_tbl}) VALUES('rebuild')"))
                            except Exception as exc:
                                logger.warning(
                                    "FTS5 rebuild after purge failed for %s: %s",
                                    fts_tbl,
                                    exc,
                                )
                            try:
                                await conn.execute(text(f"INSERT INTO {fts_tbl}({fts_tbl}) VALUES('optimize')"))
                            except Exception:
                                pass
                            result.fts_tables_purged.append(fts_tbl)

                # Collect chat ids and sandbox directories before deleting chats
                sandbox_by_chat: dict[str, str | None] = {}
                if "chats" in existing_tables:
                    async with engine.connect() as conn:
                        rows = (await conn.execute(text("SELECT id, sandbox_base_dir FROM chats"))).fetchall()
                        sandbox_by_chat = {r[0]: r[1] for r in rows}

                # Phase 2b: Conversation state goes while its chats are still listed
                for chat_id in sandbox_by_chat:
                    await chat_disposal.clear_runtime_caches(chat_id)
                    if await chat_disposal.clear_conversation_state(chat_id):
                        result.checkpoint_cleared_chats += 1

                # Phase 3: Transactional deletion of conversation corpora & cursor reset
                async with engine.begin() as conn:
                    if "messages" in existing_tables:
                        result.purged_messages = await conn.scalar(text("SELECT COUNT(*) FROM messages")) or 0
                    if "chats" in existing_tables:
                        result.purged_chats = await conn.scalar(text("SELECT COUNT(*) FROM chats")) or 0
                    if "channel_messages" in existing_tables:
                        result.purged_channel_messages = await conn.scalar(text("SELECT COUNT(*) FROM channel_messages")) or 0

                    async def _safe_delete(table_name: str) -> int:
                        if table_name not in existing_tables:
                            return 0
                        return (await conn.execute(text(f"DELETE FROM {table_name}"))).rowcount

                    # 3.1 Delete leaf conversation recall segments and documents
                    await _safe_delete("conversation_recall_segments")
                    await _safe_delete("conversation_recall_documents")

                    # 3.2 Delete conversation forks, markers and widgets
                    await _safe_delete("interrupted_turn_markers")
                    await _safe_delete("conversation_forks")
                    await _safe_delete("widget_kv_entries")

                    # 3.3 Delete core messages and chats
                    await _safe_delete("messages")
                    await _safe_delete("chats")
                    await _safe_delete("channel_messages")

                    # 3.4 Empty the memory pipeline tables if requested (stored memories, profile and rules stay)
                    if purge_memories:
                        for pipeline_table in cls.MEMORY_PIPELINE_TABLES:
                            result.purged_memory_events += await _safe_delete(pipeline_table)

                    # 3.5 Reset sqlite_sequence for wiped tables to guarantee cursor sync
                    if "sqlite_sequence" in existing_tables:
                        reset_tables = [
                            "conversation_recall_segments",
                            "conversation_recall_documents",
                            "channel_messages",
                        ]
                        for tbl in reset_tables:
                            if tbl in existing_tables:
                                await conn.execute(
                                    text("DELETE FROM sqlite_sequence WHERE name = :tbl"),
                                    {"tbl": tbl},
                                )
                                result.cursors_reset.append(tbl)

                # Phase 4: Remove the files the purged chats produced
                if purge_sandboxes:
                    result.cleared_sandboxes = await chat_disposal.remove_chat_files(sandbox_by_chat)

                # Phase 5: Reclaim physical disk pages if requested
                if reclaim_disk:
                    async with engine.connect() as conn:
                        try:
                            await conn.execute(text("PRAGMA optimize"))
                            await conn.execute(text("PRAGMA incremental_vacuum"))
                        except Exception as exc:
                            logger.warning("Disk vacuum non-fatal notice: %s", exc)

                result.success = True
                result.duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000.0
                logger.info(
                    "Safe vault purge completed successfully in %.1fms: %d chats, %d messages wiped, %d configs preserved",
                    result.duration_ms,
                    result.purged_chats,
                    result.purged_messages,
                    result.preserved_user_configs,
                )
                return result

            except Exception as e:
                logger.error("Safe vault purge failed with critical error: %s", e, exc_info=True)
                result.success = False
                result.error = str(e)
                result.duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000.0
                return result
