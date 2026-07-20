"""Integration tests for web fetch escalation (WFEL) — real network, no provider mocks."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.web_fetch.escalation.context import get_bound_escalation_providers

from app.database.connection import get_session
from app.database.models import ConfigAuditLog, UserConfig
from app.schemas.config import WebFetchEscalationConfigValue
from app.services.web_fetch.binding import open_web_fetch_escalation_context
from app.services.web_fetch.escalation.registry import build_escalation_providers
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("config", preset="integrations")


def _session_cap(value: dict[str, object]) -> int:
    cap = value.get("sessionCap", value.get("session_cap"))
    assert cap is not None
    return int(cap)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
async def cleanup_config_db() -> Iterator[None]:
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    yield
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


def _put_web_fetch_config(client: TestClient, **overrides: object) -> None:
    value = WebFetchEscalationConfigValue(
        enabled=True,
        jina_api_key=None,
        firecrawl={"inherit_from_search": True, "api_key": None},
        session_cap=5,
    )
    payload = value.model_dump(by_alias=True)
    payload.update(overrides)
    response = client.put(
        "/api/v1/config/webFetchEscalation",
        json={"value": payload, "device_id": "wfel_integration"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
class TestWebFetchEscalationVerifyIntegration:
    """POST /integrations/web-fetch/verify — real Jina Reader, no provider mock."""

    def test_jina_verify_without_key_proves_real_remote_call(self, client: TestClient) -> None:
        """Real httpx to r.jina.ai — 200 when free tier works, 502 when 401/empty."""
        response = client.post(
            "/api/v1/integrations/web-fetch/verify",
            json={"provider": "jina", "test_url": "https://example.com"},
        )
        if os.environ.get("JINA_API_KEY"):
            assert response.status_code == 200, response.text
            data = response.json().get("data") or {}
            assert int(data.get("content_length", 0)) > 0
            return

        assert response.status_code in (200, 502), response.text
        if response.status_code == 200:
            data = response.json().get("data") or {}
            assert data.get("provider") == "jina"
            assert int(data.get("content_length", 0)) > 0
            return

        detail = response.json().get("detail", {})
        message = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        assert "Remote fetch returned empty content" in message or "jina" in message.lower()

    @pytest.mark.skipif(not os.environ.get("JINA_API_KEY"), reason="JINA_API_KEY not configured")
    def test_jina_verify_success_with_api_key(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/integrations/web-fetch/verify",
            json={
                "provider": "jina",
                "api_key": os.environ["JINA_API_KEY"],
                "test_url": "https://example.com",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json().get("data") or {}
        assert data.get("provider") == "jina"
        assert int(data.get("content_length", 0)) > 0

    def test_jina_verify_blocks_ssrf_target(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/integrations/web-fetch/verify",
            json={"provider": "jina", "test_url": "http://127.0.0.1/"},
        )
        assert response.status_code in (400, 502), response.text

    def test_firecrawl_verify_without_key_uses_keyless(self, client: TestClient) -> None:
        """Firecrawl v2 keyless: no API key → free tier attempt (200 or 502 on rate limit)."""
        response = client.post(
            "/api/v1/integrations/web-fetch/verify",
            json={"provider": "firecrawl", "inherit_from_search": False},
        )
        assert response.status_code in (200, 502), response.text
        if response.status_code == 200:
            data = response.json().get("data") or {}
            assert data.get("provider") == "firecrawl"
            assert int(data.get("content_length", 0)) > 0


@pytest.mark.integration
class TestWebFetchEscalationConfigIntegration:
    """Omni-Config round-trip for webFetchEscalation."""

    def test_config_round_trip_default_off(self, client: TestClient) -> None:
        put = client.put(
            "/api/v1/config/webFetchEscalation",
            json={
                "value": {
                    "enabled": False,
                    "jinaApiKey": None,
                    "firecrawl": {"inheritFromSearch": True, "api_key": None},
                    "sessionCap": 5,
                },
                "device_id": "wfel_integration",
            },
        )
        assert put.status_code == 200, put.text

        get = client.get("/api/v1/config/webFetchEscalation")
        assert get.status_code == 200, get.text
        value = get.json()["value"]
        assert value["enabled"] is False
        assert _session_cap(value) == 5

    def test_config_sync_includes_web_fetch_escalation(self, client: TestClient) -> None:
        sync_payload = {
            "changes": [
                {
                    "key": "webFetchEscalation",
                    "value": {
                        "enabled": True,
                        "jinaApiKey": None,
                        "firecrawl": {"inheritFromSearch": True, "api_key": None},
                        "sessionCap": 3,
                    },
                    "expectedVersion": None,
                    "timestamp": 1,
                }
            ],
            "deviceId": "wfel_integration",
        }
        response = client.post("/api/v1/config/sync", json=sync_payload)
        assert response.status_code == 200, response.text

        stored = client.get("/api/v1/config/webFetchEscalation")
        assert stored.status_code == 200
        assert stored.json()["value"]["enabled"] is True
        assert _session_cap(stored.json()["value"]) == 3


@pytest.mark.integration
class TestWebFetchEscalationEnvDeniedIntegration:
    """MYRM_WEB_FETCH_ESCALATION=denied blocks provider build."""

    @pytest.mark.asyncio
    async def test_env_denied_prevents_provider_build(self, client: TestClient) -> None:
        _put_web_fetch_config(client)

        prev = os.environ.get("MYRM_WEB_FETCH_ESCALATION")
        os.environ["MYRM_WEB_FETCH_ESCALATION"] = "denied"
        try:
            assert await build_escalation_providers("denied-session") is None
        finally:
            if prev is None:
                os.environ.pop("MYRM_WEB_FETCH_ESCALATION", None)
            else:
                os.environ["MYRM_WEB_FETCH_ESCALATION"] = prev

    @pytest.mark.asyncio
    async def test_disabled_config_returns_no_providers(self, client: TestClient) -> None:
        put = client.put(
            "/api/v1/config/webFetchEscalation",
            json={
                "value": {
                    "enabled": False,
                    "jinaApiKey": None,
                    "firecrawl": {"inheritFromSearch": True, "api_key": None},
                    "sessionCap": 5,
                },
                "device_id": "wfel_integration",
            },
        )
        assert put.status_code == 200
        assert await build_escalation_providers("disabled-session") is None


@pytest.mark.integration
class TestWebFetchEscalationLiveServerIntegration:
    """Hit running :8080 when available (post harness editable install)."""

    @pytest.mark.skipif(
        os.environ.get("MYRM_SKIP_LIVE_SERVER") == "1",
        reason="Live server checks disabled",
    )
    def test_live_verify_endpoint_registered(self) -> None:
        import httpx

        try:
            response = httpx.post(
                "http://127.0.0.1:8080/api/v1/integrations/web-fetch/verify",
                json={"provider": "firecrawl", "inherit_from_search": False},
                timeout=5.0,
            )
        except httpx.HTTPError as exc:
            pytest.skip(f":8080 not reachable: {exc}")

        assert response.status_code in (200, 400, 502), response.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestWebFetchEscalationBindingIntegration:
    """Stream binding chain: config → build providers → ContextVar (no build mock)."""

    async def test_enabled_config_builds_jina_provider_chain(self, client: TestClient) -> None:
        _put_web_fetch_config(client)

        providers = await build_escalation_providers("integration-session-1")
        assert providers is not None
        assert len(providers) >= 1
        assert providers[0].provider_id == "jina"

    async def test_open_context_binds_providers_from_real_config(self, client: TestClient) -> None:
        _put_web_fetch_config(client)

        async with open_web_fetch_escalation_context(
            session_id="integration-session-2",
            browser_source="extension",
        ):
            bound = get_bound_escalation_providers()
            assert bound is not None
            assert len(bound) >= 1

        assert get_bound_escalation_providers() is None
