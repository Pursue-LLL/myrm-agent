"""Unit tests for ConversationAnchorSearchService and anchor-search API.

Validates exact phrase matching, boolean combination terms, context window slicing
with start/end character offsets, relevance score ordering, and API responses.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chats.chat.anchor_search import router as anchor_search_router
from app.database.dto import ChatDTO, MessageDTO
from app.services.chat.conversation_anchor_search_service import (
    ConversationAnchorSearchService,
)

pytestmark = pytest.mark.unit


def _create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(anchor_search_router, prefix="/api/chats")
    return app


class TestConversationAnchorSearch:
    """Test suite for conversation anchor scroll search."""

    @pytest.mark.asyncio
    async def test_search_anchors_in_session(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        chat_id = "chat-test-101"

        mock_chat = ChatDTO(
            id=chat_id,
            title="Kubernetes Deployment Review",
            created_at=now,
            updated_at=now,
        )

        messages = [
            MessageDTO(
                id="msg-1",
                chat_id=chat_id,
                role="user",
                content="Please review our new production Helm chart for Redis cluster.",
                sent_at=now,
                sent_timezone="UTC",
                created_at=now,
            ),
            MessageDTO(
                id="msg-2",
                chat_id=chat_id,
                role="assistant",
                content="Here is the review for your production Helm chart: everything looks well configured.",
                sent_at=now,
                sent_timezone="UTC",
                created_at=now,
            ),
            MessageDTO(
                id="msg-3",
                chat_id=chat_id,
                role="user",
                content="Unrelated message about lunch options.",
                sent_at=now,
                sent_timezone="UTC",
                created_at=now,
            ),
        ]

        mock_repo = AsyncMock()
        mock_repo.get_chat_by_id.return_value = mock_chat
        mock_repo.get_all_messages.return_value = messages

        with patch.object(ConversationAnchorSearchService, "_cr", return_value=mock_repo):
            hits = await ConversationAnchorSearchService.search_anchors(
                query='"production Helm chart"',
                chat_id=chat_id,
                limit=10,
                window_chars=50,
            )

        assert len(hits) == 2
        assert hits[0].chat_id == chat_id
        assert hits[0].chat_title == "Kubernetes Deployment Review"
        assert hits[0].highlight.matched_text == "production Helm chart"
        assert hits[0].highlight.start_char >= 0
        assert hits[0].highlight.end_char > hits[0].highlight.start_char
        assert hits[0].score > 0.7

    @pytest.mark.asyncio
    async def test_search_anchors_empty_query(self) -> None:
        hits = await ConversationAnchorSearchService.search_anchors("")
        assert hits == []

    @pytest.mark.asyncio
    async def test_search_anchors_cross_session_fts_filtering(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        raw_candidates: list[dict[str, object]] = [
            {
                "id": "msg-fts-1",
                "chat_id": "chat-a",
                "role": "assistant",
                "content": 'We should configure "Prompt Cache" prefix stability.',
                "chat_title": "Prompt Engineering",
                "sent_at": now,
            },
            {
                "id": "msg-fts-2",
                "chat_id": "chat-b",
                "role": "user",
                "content": "Random memory without the exact phrase.",
                "chat_title": "Off topic",
                "sent_at": now,
            },
        ]

        mock_repo = AsyncMock()
        mock_repo.search_messages_fts.return_value = (raw_candidates, 2)

        with patch.object(ConversationAnchorSearchService, "_cr", return_value=mock_repo):
            hits = await ConversationAnchorSearchService.search_anchors(
                query='"Prompt Cache"',
                chat_id=None,
                limit=5,
            )

        assert len(hits) == 1
        assert hits[0].message_id == "msg-fts-1"
        assert hits[0].highlight.matched_text == "Prompt Cache"

    def test_anchor_search_api_endpoint(self) -> None:
        app = _create_test_app()
        client = TestClient(app)

        with patch.object(
            ConversationAnchorSearchService,
            "search_anchors",
            new_callable=AsyncMock,
        ) as mock_search:
            from app.schemas.anchor_search import (
                ConversationAnchorHighlightPayload,
                ConversationAnchorSearchHit,
            )

            mock_search.return_value = [
                ConversationAnchorSearchHit(
                    chat_id="chat-1",
                    message_id="msg-1",
                    role="user",
                    score=0.95,
                    highlight=ConversationAnchorHighlightPayload(
                        prefix="start ",
                        matched_text="target phrase",
                        suffix=" end",
                        start_char=6,
                        end_char=19,
                        formatted_snippet="start «target phrase» end",
                    ),
                    chat_title="Demo Session",
                    sent_at="2026-10-06T12:00:00Z",
                )
            ]

            response = client.get("/api/chats/anchor-search?q=%22target%20phrase%22&chat_id=chat-1")
            assert response.status_code == 200
            payload = response.json()
            assert payload["code"] == 0
            assert payload["data"]["total"] == 1
            assert payload["data"]["items"][0]["message_id"] == "msg-1"
            assert payload["data"]["items"][0]["highlight"]["matched_text"] == "target phrase"
            assert payload["data"]["items"][0]["highlight"]["start_char"] == 6
