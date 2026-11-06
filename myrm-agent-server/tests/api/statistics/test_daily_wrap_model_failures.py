"""A failed model call behind the daily-wrap endpoints is reported by what the provider answered.

The route's catch-all answers HTTP 500 with the AI business code of the failure and a message that does not carry the
provider's own text, whatever the failure is: a rejected key, a rate limit, an overloaded provider, an unreadable answer
or a silent provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError

from app.schemas.responses import BusinessCode
from tests.support.minimal_app import build_minimal_app
from tests.support.provider_failures import provider_failure

_SECRET = "sk-live-0123456789abcdef"
_REJECTED = f"{_SECRET} is not valid for org-acme"
_SESSIONS = [{"title": "Code Review", "action_mode": "chat", "total_tokens": 5000, "total_usd": 0.01}]
_ROUTES = [
    ("GET", "/api/v1/statistics/daily-wrap", "Get daily wrap"),
    ("POST", "/api/v1/statistics/daily-wrap/regenerate", "Regenerate daily wrap"),
]


@contextmanager
def _day_with_activity_whose_model_fails(error: Exception) -> Iterator[None]:
    configs = MagicMock()
    configs.providers_dict = {"mock": "provider"}
    lite_model = MagicMock()
    lite_model.model = "gpt-4o-mini"
    lite_model.base_url = None
    lite_model.api_key = "sk-test"
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(side_effect=error)

    with (
        patch("app.api.statistics.daily_wrap._fetch_sessions", new_callable=AsyncMock, return_value=_SESSIONS),
        patch("app.api.statistics.daily_wrap._fetch_approvals", new_callable=AsyncMock, return_value=[]),
        patch("app.api.statistics.daily_wrap._fetch_cron_runs", new_callable=AsyncMock, return_value=[]),
        patch("app.api.statistics.daily_wrap._fetch_kanban_events", new_callable=AsyncMock, return_value=[]),
        patch("app.core.channel_bridge.config_loader.load_user_configs", new_callable=AsyncMock, return_value=configs),
        patch("app.core.channel_bridge.config_parsers.extract_lite_model_config", return_value=lite_model),
        patch("myrm_agent_harness.toolkits.llms.create_chat_model", return_value=llm),
    ):
        yield


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=build_minimal_app(preset="statistics"))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "route", "operation"), _ROUTES)
@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (provider_failure(401, _REJECTED), BusinessCode.AI_AUTH_ERROR),
        (provider_failure(429, _REJECTED), BusinessCode.AI_RATE_LIMIT_ERROR),
        (provider_failure(503, _REJECTED), BusinessCode.AI_MODEL_ERROR),
        (LLMResponseError("openai", "openai answered with a non-JSON body: '<html>'"), BusinessCode.AI_MODEL_ERROR),
        (httpx.ReadTimeout("provider stayed silent"), BusinessCode.AI_TIMEOUT_ERROR),
    ],
)
async def test_a_failed_model_call_is_a_500_named_by_what_the_provider_answered(
    client: AsyncClient, method: str, route: str, operation: str, failure: Exception, code: BusinessCode
) -> None:
    with _day_with_activity_whose_model_fails(failure):
        response = await client.request(method, route, params={"date": "2026-06-12"})

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == code.value
    assert response.json()["detail"]["message"].startswith(f"{operation} failed: AI ")
    assert _SECRET not in response.text


@pytest.mark.asyncio
async def test_a_failure_that_is_not_the_model_stays_a_plain_internal_error(client: AsyncClient) -> None:
    with patch("app.api.statistics.daily_wrap._fetch_sessions", new_callable=AsyncMock, side_effect=RuntimeError("disk")):
        response = await client.get("/api/v1/statistics/daily-wrap", params={"date": "2026-06-12"})

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == BusinessCode.INTERNAL_ERROR.value
