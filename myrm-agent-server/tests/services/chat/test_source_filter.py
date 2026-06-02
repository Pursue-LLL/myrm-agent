"""
Tests for chat history source filtering functionality.
Covers: ChatRepository.get_chats_paginated with source parameter.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from app.database.models import Chat
from app.database.repositories.chat_repo import ChatRepository
from app.services.chat.chat_service import ChatService


@pytest_asyncio.fixture
async def seed_chats(db_session):
    """Seed test chats with different sources."""
    chats = [
        Chat(id=str(uuid4()), title="Web Chat 1", source="web", action_mode="fast",
             created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), updated_at=datetime(2026, 1, 5, tzinfo=timezone.utc)),
        Chat(id=str(uuid4()), title="Web Chat 2", source="web", action_mode="fast",
             created_at=datetime(2026, 1, 2, tzinfo=timezone.utc), updated_at=datetime(2026, 1, 4, tzinfo=timezone.utc)),
        Chat(id=str(uuid4()), title="Telegram Chat 1", source="telegram", action_mode="fast",
             created_at=datetime(2026, 1, 3, tzinfo=timezone.utc), updated_at=datetime(2026, 1, 3, tzinfo=timezone.utc)),
        Chat(id=str(uuid4()), title="Feishu Chat 1", source="feishu", action_mode="fast",
             created_at=datetime(2026, 1, 4, tzinfo=timezone.utc), updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        Chat(id=str(uuid4()), title="Discord Chat 1", source="discord", action_mode="fast",
             created_at=datetime(2026, 1, 5, tzinfo=timezone.utc), updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ]
    db_session.add_all(chats)
    await db_session.commit()
    return chats


class TestChatRepositorySourceFilter:
    """Test ChatRepository.get_chats_paginated source filtering."""

    @pytest.mark.asyncio
    async def test_no_filter_returns_all(self, db_session, seed_chats):
        """Without source filter, returns all chats."""
        results, total = await ChatRepository.get_chats_paginated(db_session, 0, 10)
        assert total == 5
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_filter_by_web(self, db_session, seed_chats):
        """Filter by source='web' returns only web chats."""
        results, total = await ChatRepository.get_chats_paginated(db_session, 0, 10, source="web")
        assert total == 2
        assert all(r.source == "web" for r in results)

    @pytest.mark.asyncio
    async def test_filter_by_telegram(self, db_session, seed_chats):
        """Filter by source='telegram' returns only telegram chats."""
        results, total = await ChatRepository.get_chats_paginated(db_session, 0, 10, source="telegram")
        assert total == 1
        assert results[0].source == "telegram"
        assert results[0].title == "Telegram Chat 1"

    @pytest.mark.asyncio
    async def test_filter_nonexistent_source(self, db_session, seed_chats):
        """Filter by nonexistent source returns empty results."""
        results, total = await ChatRepository.get_chats_paginated(db_session, 0, 10, source="slack")
        assert total == 0
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_filter_with_pagination(self, db_session, seed_chats):
        """Source filter works correctly with pagination."""
        results_page1, total = await ChatRepository.get_chats_paginated(db_session, 0, 1, source="web")
        assert total == 2
        assert len(results_page1) == 1

        results_page2, total2 = await ChatRepository.get_chats_paginated(db_session, 1, 1, source="web")
        assert total2 == 2
        assert len(results_page2) == 1
        assert results_page1[0].id != results_page2[0].id

    @pytest.mark.asyncio
    async def test_filter_preserves_order(self, db_session, seed_chats):
        """Filtered results are ordered by updated_at desc."""
        results, _ = await ChatRepository.get_chats_paginated(db_session, 0, 10, source="web")
        assert len(results) == 2
        assert results[0].updated_at >= results[1].updated_at

    @pytest.mark.asyncio
    async def test_none_source_same_as_no_filter(self, db_session, seed_chats):
        """Passing source=None is equivalent to no filter."""
        results, total = await ChatRepository.get_chats_paginated(db_session, 0, 10, source=None)
        assert total == 5


class TestChatServiceSourceFilter:
    """Test ChatService.get_chat_list source filtering via UoW."""

    @pytest.mark.asyncio
    async def test_service_passes_source_to_repo(self, db_session, seed_chats):
        """ChatService correctly passes source parameter through to repository."""
        results, total = await ChatService.get_chat_list(page=1, page_size=10, source="telegram")
        assert total == 1
        assert results[0].source == "telegram"

    @pytest.mark.asyncio
    async def test_service_no_filter(self, db_session, seed_chats):
        """ChatService returns all chats when source is None."""
        results, total = await ChatService.get_chat_list(page=1, page_size=10, source=None)
        assert total == 5

    @pytest.mark.asyncio
    async def test_service_pagination_with_source(self, db_session, seed_chats):
        """ChatService pagination respects source filter for total count."""
        results, total = await ChatService.get_chat_list(page=1, page_size=1, source="web")
        assert total == 2
        assert len(results) == 1
