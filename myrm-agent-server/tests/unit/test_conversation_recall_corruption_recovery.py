"""Unit tests for ConversationRecallRepository corruption resilience and health checking."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.repositories.conversation_recall.repo import (
    ConversationRecallRepository,
)


@pytest.mark.asyncio
async def test_conversation_recall_health_detects_corrupted_fts() -> None:
    db = AsyncMock()

    # Mock count queries
    count_row = {"indexed_conversations": 10, "excluded_conversations": 0, "last_indexed_at": None}
    db.execute.side_effect = [
        # 1. doc counts
        MagicMock(mappings=MagicMock(return_value=MagicMock(one=MagicMock(return_value=count_row)))),
        # 2. missing count
        MagicMock(scalar_one=MagicMock(return_value=0)),
        # 3. segment_count
        MagicMock(scalar_one=MagicMock(return_value=20)),
        # 4. missing_segments
        MagicMock(scalar_one=MagicMock(return_value=0)),
        # 5. fts_ready table check
        MagicMock(scalar_one=MagicMock(return_value=1)),
        # 6. segments_fts_ready table check
        MagicMock(scalar_one=MagicMock(return_value=1)),
        # 7. fts integrity-check throws error
        RuntimeError("database disk image is malformed"),
        # 8. segments_fts integrity-check succeeds
        MagicMock(),
    ]

    health = await ConversationRecallRepository.health(db)
    assert health.fts_ready is False
    assert health.segments_fts_ready is True
    assert health.indexed_conversations == 10
    assert health.indexed_segments == 20
