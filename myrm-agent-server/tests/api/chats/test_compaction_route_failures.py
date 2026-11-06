"""A failed summary model behind the compact-chat endpoint is reported by what the provider answered.

The endpoint turns a ``ValueError`` into "invalid request" (400) and everything else into its catch-all (500). A
provider's failure is not the caller's invalid input, so an unreadable provider answer takes the catch-all too.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError, LLMResponseError

from app.api.chats.chat.compaction import router
from app.database.connection import get_db
from app.schemas.responses import BusinessCode

_SECRET = "sk-live-0123456789abcdef"
_ROUTE = "/chat-1/compact"


def _provider_failure(status: int) -> LLMHTTPError:
    body = json.dumps({"error": {"message": f"{_SECRET} is not valid for org-acme"}})
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    return LLMHTTPError("openai", status, body, httpx.Response(status, content=body.encode(), request=request))


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)

    async def _no_db() -> None:
        return None

    app.dependency_overrides[get_db] = _no_db
    with TestClient(app) as test_client:
        yield test_client


def _compaction_raising(error: Exception):
    return patch("app.services.chat.compact_service.compact_chat", new=AsyncMock(side_effect=error))


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (_provider_failure(401), BusinessCode.AI_AUTH_ERROR),
        (_provider_failure(429), BusinessCode.AI_RATE_LIMIT_ERROR),
        (_provider_failure(503), BusinessCode.AI_MODEL_ERROR),
        (LLMResponseError("openai", "openai answered with a non-JSON body: '<html>'"), BusinessCode.AI_MODEL_ERROR),
        (httpx.ConnectTimeout("provider unreachable"), BusinessCode.AI_TIMEOUT_ERROR),
    ],
)
def test_a_failed_summary_model_is_a_500_named_by_what_the_provider_answered(
    client: TestClient, failure: Exception, code: BusinessCode
) -> None:
    with _compaction_raising(failure):
        response = client.post(_ROUTE)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == code.value
    assert response.json()["detail"]["message"].startswith("Compact chat context failed: AI ")
    assert _SECRET not in response.text


def test_an_invalid_request_is_still_a_400(client: TestClient) -> None:
    with _compaction_raising(ValueError("Cannot resolve before_message_id for chat_id=chat-1")):
        response = client.post(_ROUTE)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == BusinessCode.VALIDATION_ERROR.value
