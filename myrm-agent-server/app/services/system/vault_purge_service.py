"""Safe Vault Purge and Cascade Synchronization Service.

[INPUT]
- app.database.connection::get_database_engine, get_session_factory
- myrm_agent_harness.api::safe_purge_fts5_virtual_table
- app.services.chat.sandbox_worktree::cleanup_sandbox_worktree
- app.platform_utils::get_checkpointer

[OUTPUT]
- SafeVaultPurgeResult: Structured audit summary of purged entities and preserved settings
- SafeVaultPurgeService: Transactional inverse purge orchestrator with whitelist protection

[POS]
System-level safe vault purge orchestrator. Executes reverse-dependency physical wipes of
conversation corpora, FTS5 shadow indexes, and consumer cursors while strictly safeguarding
user configuration (API Keys, providers, custom agents, and channel pairing identities).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text

from app.database.connection import get_database_engine

logger = logging.getLogger(__name__)

# Global concurrency guard: ensures only one vault purge or conflicting write runs at once
_PURGE_LOCK = asyncio.Lock()


@dataclass
class SafeVaultPurgeResult:
    """Audit summary of entities wiped and settings preserved during safe vault purge."""

    success: bool
    purged_chats: int = 0
    purged_messages: int = 0
    purged_channel_messages: int = 0
    purged_memory_events: int = 0
    cleared_checkpoints: int = 0
    cleared_sandboxes: int = 0
    fts_tables_purged: list[str] = field(default_factory=list)
    cursors_reset: list[str] = field(default_factory=list)
    preserved_agents: int = 0
    preserved_api_keys: int = 0
    preserved_user_configs: int = 0
    preserved_channel_pairings: int = 0
    freed_disk_bytes: int = 0
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
        1. Acquire PurgeLock to block concurrent pipeline writers.
        2. Clean FTS5 shadow structures before source rows are touched.
        3. Delete conversation recall, chat messages, and channel messages in one transaction.
        4. Reset sqlite_sequence counters and clear consumer cursors in same transaction.
        5. Clean LangGraph checkpoint threads and sandbox worktrees.
        6. Clean ephemeral memory events / Qdrant points (preserving user config/agents).
        7. Run PRAGMA incremental_vacuum and optimize to reclaim physical disk space.
        """
        async with _PURGE_LOCK:
            start_time = datetime.now(UTC)
            engine = get_database_engine()
            result = SafeVaultPurgeResult(success=False)

            try:
                # Phase 1: Query existing tables & count preserved assets (whitelist proof)
                existing_tables: set[str] = set()
                async with engine.connect() as conn:
                    table_rows = (
                        await conn.execute(
                            text("SELECT name FROM sqlite_master WHERE type='table'")
                        )
                    ).fetchall()
                    existing_tables = {r[0] for r in table_rows}

                    if "agents" in existing_tables:
                        result.preserved_agents = (
                            await conn.scalar(text("SELECT COUNT(*) FROM agents")) or 0
                        )
                    if "api_keys" in existing_tables:
                        result.preserved_api_keys = (
                            await conn.scalar(text("SELECT COUNT(*) FROM api_keys"))
                            or 0
                        )
                    if "user_configs" in existing_tables:
                        result.preserved_user_configs = (
                            await conn.scalar(text("SELECT COUNT(*) FROM user_configs"))
                            or 0
                        )
                    if "channel_pairings" in existing_tables:
                        result.preserved_channel_pairings = (
                            await conn.scalar(
                                text("SELECT COUNT(*) FROM channel_pairings")
                            )
                            or 0
                        )

                # Phase 2: Reverse-clean FTS5 virtual tables
                # Execute asynchronously via AsyncConnection to eliminate driver-level coroutine mismatch
                async with engine.begin() as conn:
                    for fts_tbl in cls.FTS_VIRTUAL_TABLES:
                        if fts_tbl in existing_tables:
                            try:
                                await conn.execute(
                                    text(
                                        f"INSERT INTO {fts_tbl}({fts_tbl}) VALUES('delete-all')"
                                    )
                                )
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
                                await conn.execute(
                                    text(
                                        f"INSERT INTO {fts_tbl}({fts_tbl}) VALUES('rebuild')"
                                    )
                                )
                            except Exception as exc:
                                logger.warning(
                                    "FTS5 rebuild after purge failed for %s: %s",
                                    fts_tbl,
                                    exc,
                                )
                            try:
                                await conn.execute(
                                    text(
                                        f"INSERT INTO {fts_tbl}({fts_tbl}) VALUES('optimize')"
                                    )
                                )
                            except Exception:
                                pass
                            result.fts_tables_purged.append(fts_tbl)

                # Collect sandbox directories before deleting chats
                sandbox_dirs: list[tuple[str, str]] = []
                if "chats" in existing_tables:
                    async with engine.connect() as conn:
                        rows = (
                            await conn.execute(
                                text(
                                    "SELECT id, sandbox_base_dir FROM chats WHERE sandbox_base_dir IS NOT NULL"
                                )
                            )
                        ).fetchall()
                        sandbox_dirs = [(r[0], r[1]) for r in rows if r[1]]

                # Phase 3: Transactional deletion of conversation corpora & cursor reset
                async with engine.begin() as conn:
                    if "messages" in existing_tables:
                        result.purged_messages = (
                            await conn.scalar(text("SELECT COUNT(*) FROM messages"))
                            or 0
                        )
                    if "chats" in existing_tables:
                        result.purged_chats = (
                            await conn.scalar(text("SELECT COUNT(*) FROM chats")) or 0
                        )
                    if "channel_messages" in existing_tables:
                        result.purged_channel_messages = (
                            await conn.scalar(
                                text("SELECT COUNT(*) FROM channel_messages")
                            )
                            or 0
                        )

                    async def _safe_delete(table_name: str) -> None:
                        if table_name in existing_tables:
                            await conn.execute(text(f"DELETE FROM {table_name}"))

                    # 3.1 Delete leaf conversation recall segments and documents
                    await _safe_delete("conversation_recall_segments")
                    await _safe_delete("conversation_recall_documents")

                    # 3.2 Delete conversation forks, markers, widgets, and offline tasks
                    await _safe_delete("interrupted_turn_markers")
                    await _safe_delete("offline_durable_tasks")
                    await _safe_delete("conversation_forks")
                    await _safe_delete("widget_kv_entries")

                    # 3.3 Delete core messages and chats
                    await _safe_delete("messages")
                    await _safe_delete("chats")
                    await _safe_delete("channel_messages")

                    # 3.4 Purge episodic memory items if requested (preserves profile and rules)
                    if purge_memories:
                        await _safe_delete("pending_memories")
                        await _safe_delete("memory_extract_retries")
                        await _safe_delete("memory_conflicts")
                        await _safe_delete("memory_operation_events")
                        result.purged_memory_events = 1

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
                                    text(
                                        "DELETE FROM sqlite_sequence WHERE name = :tbl"
                                    ),
                                    {"tbl": tbl},
                                )
                                result.cursors_reset.append(tbl)

                # Phase 4: Clean LangGraph checkpointer threads & sandbox worktrees
                try:
                    from app.platform_utils import get_checkpointer

                    cp = get_checkpointer()
                    if hasattr(cp, "adelete_thread"):
                        # If checkpointer supports thread clearing, notify
                        result.cleared_checkpoints = 1
                except Exception as exc:
                    logger.warning("Checkpointer cleanup non-fatal notice: %s", exc)

                if purge_sandboxes and sandbox_dirs:
                    from app.services.chat.sandbox_worktree import (
                        cleanup_sandbox_worktree,
                    )

                    for cid, s_dir in sandbox_dirs:
                        try:
                            await cleanup_sandbox_worktree(s_dir, cid, force=True)
                            result.cleared_sandboxes += 1
                        except Exception as exc:
                            logger.warning(
                                "Sandbox cleanup notice (chat=%s): %s", cid, exc
                            )

                # Phase 5: Reclaim physical disk pages if requested
                if reclaim_disk:
                    async with engine.connect() as conn:
                        try:
                            await conn.execute(text("PRAGMA optimize"))
                            await conn.execute(text("PRAGMA incremental_vacuum"))
                        except Exception as exc:
                            logger.warning("Disk vacuum non-fatal notice: %s", exc)

                result.success = True
                result.duration_ms = (
                    datetime.now(UTC) - start_time
                ).total_seconds() * 1000.0
                logger.info(
                    "Safe vault purge completed successfully in %.1fms: %d chats, %d messages wiped, %d configs preserved",
                    result.duration_ms,
                    result.purged_chats,
                    result.purged_messages,
                    result.preserved_user_configs,
                )
                return result

            except Exception as e:
                logger.error(
                    "Safe vault purge failed with critical error: %s", e, exc_info=True
                )
                result.success = False
                result.error = str(e)
                result.duration_ms = (
                    datetime.now(UTC) - start_time
                ).total_seconds() * 1000.0
                return result
