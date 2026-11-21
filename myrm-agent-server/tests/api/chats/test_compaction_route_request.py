"""The compact-chat endpoint is a person's request: it reaches the service as one and answers with the service's own reason."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import ANY, AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chats.chat.compaction import router
from app.database.connection import get_db
from app.services.chat.compact_service import CompactReason, CompactResult

_ROUTE = "/chat-1/compact"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)

    async def _no_db() -> None:
        return None

    app.dependency_overrides[get_db] = _no_db
    with TestClient(app) as test_client:
        yield test_client


def test_the_request_reaches_the_service_as_a_persons_request(client: TestClient) -> None:
    compaction = AsyncMock(return_value=CompactResult(compacted=True, message_count=12, tokens_saved=3400))

    with patch("app.services.chat.compact_service.compact_chat", new=compaction):
        response = client.post(_ROUTE, json={"focus_topic": "  billing  "})

    assert response.status_code == 200
    compaction.assert_awaited_once_with(ANY, "chat-1", focus_topic="billing", explicit_request=True)
    assert response.json()["data"]["tokens_saved"] == 3400


@pytest.mark.parametrize("reason", list(CompactReason))
def test_a_compaction_that_did_not_happen_answers_with_the_bare_reason_code(client: TestClient, reason: CompactReason) -> None:
    compaction = AsyncMock(return_value=CompactResult(compacted=False, message_count=3, reason=reason))

    with patch("app.services.chat.compact_service.compact_chat", new=compaction):
        response = client.post(_ROUTE)

    data = response.json()["data"]
    assert (data["compacted"], data["reason"]) == (False, reason.value)
