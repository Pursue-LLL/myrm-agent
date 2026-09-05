"""Unit tests for SafeVaultPurgeService.

Tests reverse-dependency wipe sequence, FTS5 virtual table purging,
cursor reset, and strict whitelist preservation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.system.vault_purge_service import (
    SafeVaultPurgeResult,
    SafeVaultPurgeService,
)


@pytest.mark.asyncio
async def test_purge_vault_orchestration_success() -> None:
    """Purge vault executes Phase 1 to Phase 5 in order and preserves whitelist."""
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_raw_conn = MagicMock()
    mock_db_api_conn = MagicMock()
    mock_raw_conn.driver_connection = mock_db_api_conn

    # Setup connection context managers
    mock_conn.get_raw_connection = AsyncMock(return_value=mock_raw_conn)
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_tx_conn = AsyncMock()
    mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_tx_conn)
    mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    # Scalar returns for counts
    # Phase 1: 4 counts (agents=5, api_keys=2, user_configs=3, channel_pairings=1)
    mock_conn.scalar = AsyncMock(
        side_effect=[
            5,  # agents
            2,  # api_keys
            3,  # user_configs
            1,  # channel_pairings
        ]
    )
    mock_tx_conn.scalar = AsyncMock(
        side_effect=[
            150,  # messages
            10,  # chats
            25,  # channel_messages
        ]
    )

    all_tables = [
        ("agents",),
        ("api_keys",),
        ("user_configs",),
        ("channel_pairings",),
        ("chats",),
        ("messages",),
        ("channel_messages",),
        ("conversation_recall_segments_fts",),
        ("conversation_recall_fts",),
        ("messages_fts",),
        ("conversation_recall_segments",),
        ("conversation_recall_documents",),
        ("interrupted_turn_markers",),
        ("offline_durable_tasks",),
        ("conversation_forks",),
        ("widget_kv_entries",),
        ("pending_memories",),
        ("memory_extract_retries",),
        ("memory_conflicts",),
        ("memory_operation_events",),
        ("sqlite_sequence",),
    ]

    async def mock_execute(statement, *args, **kwargs):
        stmt_str = str(statement)
        cursor = MagicMock()
        if "sqlite_master" in stmt_str:
            cursor.fetchall.return_value = all_tables
        elif "sandbox_base_dir" in stmt_str:
            cursor.fetchall.return_value = [("chat-1", "/tmp/sandbox-1")]
        else:
            cursor.fetchall.return_value = []
        return cursor

    mock_conn.execute = AsyncMock(side_effect=mock_execute)

    with (
        patch(
            "app.services.system.vault_purge_service.get_database_engine",
            return_value=mock_engine,
        ),
        patch("app.services.system.vault_purge_service.safe_purge_fts5_virtual_table") as mock_fts_purge,
        patch(
            "app.services.chat.sandbox_worktree.cleanup_sandbox_worktree",
            new_callable=AsyncMock,
        ) as mock_cleanup_sandbox,
    ):
        result = await SafeVaultPurgeService.purge_vault(
            purge_memories=True,
            purge_sandboxes=True,
            reclaim_disk=True,
        )

    assert isinstance(result, SafeVaultPurgeResult)
    assert result.success is True
    assert result.purged_chats == 10
    assert result.purged_messages == 150
    assert result.purged_channel_messages == 25
    assert result.preserved_agents == 5
    assert result.preserved_api_keys == 2
    assert result.preserved_user_configs == 3
    assert result.preserved_channel_pairings == 1
    assert len(result.fts_tables_purged) == 3
    assert "messages_fts" in result.fts_tables_purged
    assert len(result.cursors_reset) == 3
    assert result.cleared_sandboxes == 1
    assert mock_fts_purge.call_count == 3
    mock_cleanup_sandbox.assert_awaited_once_with("/tmp/sandbox-1", "chat-1", force=True)


@pytest.mark.asyncio
async def test_purge_vault_handles_critical_database_error() -> None:
    """Purge vault catches critical database error, records failure, and does not raise."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = RuntimeError("Database I/O disk failure")

    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=mock_engine,
    ):
        result = await SafeVaultPurgeService.purge_vault()

    assert result.success is False
    assert "Database I/O disk failure" in (result.error or "")
