"""Tests for Feishu QR registration API endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.channels.feishu_register import (
    _SESSION_TTL_S,
    _active_sessions,
    _cleanup_expired_sessions,
    _RegistrationSession,
)


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    """Ensure session store is empty before each test."""
    _active_sessions.clear()


def _mock_begin_result() -> dict[str, Any]:
    return {
        "qr_url": "https://feishu.cn/scan?code=test123&from=myrm&tp=myrm",
        "device_code": "dc_test_001",
        "user_code": "TEST01",
        "interval": 5,
        "expire_in": 300,
    }


def _mock_poll_success() -> dict[str, Any]:
    return {
        "status": "success",
        "credentials": {
            "app_id": "cli_test_abc",
            "app_secret": "secret_test_xyz",
            "domain": "feishu",
            "open_id": "ou_test_123",
            "bot_name": None,
            "bot_open_id": None,
        },
        "domain": "feishu",
    }


def _mock_poll_pending() -> dict[str, Any]:
    return {"status": "pending", "credentials": None, "domain": "feishu"}


def _mock_poll_denied() -> dict[str, Any]:
    return {"status": "denied", "credentials": None, "domain": "feishu"}


def _mock_poll_expired() -> dict[str, Any]:
    return {"status": "expired", "credentials": None, "domain": "feishu"}


@pytest.fixture
def app() -> Any:
    """Create test FastAPI app with feishu registration router."""
    from fastapi import FastAPI

    from app.api.channels.feishu_register import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/channels/manage")
    return test_app


@pytest.fixture
async def client(app: Any) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c  # type: ignore[misc]


class TestStartQRRegister:
    @pytest.mark.asyncio
    async def test_start_success(self, client: AsyncClient) -> None:
        mock_reg = AsyncMock()
        mock_reg.begin.return_value = _mock_begin_result()

        with patch(
            "app.channels.providers.feishu.registration.FeishuAppRegistration",
            return_value=mock_reg,
        ):
            resp = await client.post("/channels/manage/feishu/qr-register")

        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["qr_url"] == _mock_begin_result()["qr_url"]
        assert data["expire_in"] == 300
        assert data["interval"] == 5
        assert len(_active_sessions) == 1

    @pytest.mark.asyncio
    async def test_start_runtime_error_returns_503(self, client: AsyncClient) -> None:
        mock_reg = AsyncMock()
        mock_reg.begin.side_effect = RuntimeError("does not support client_secret")

        with patch(
            "app.channels.providers.feishu.registration.FeishuAppRegistration",
            return_value=mock_reg,
        ):
            resp = await client.post("/channels/manage/feishu/qr-register")

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_start_unexpected_error_returns_500(self, client: AsyncClient) -> None:
        mock_reg = AsyncMock()
        mock_reg.begin.side_effect = ValueError("unexpected")

        with patch(
            "app.channels.providers.feishu.registration.FeishuAppRegistration",
            return_value=mock_reg,
        ):
            resp = await client.post("/channels/manage/feishu/qr-register")

        assert resp.status_code == 500


class TestPollQRRegister:
    @pytest.mark.asyncio
    async def test_poll_session_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/channels/manage/feishu/qr-register/poll",
            json={"session_id": "nonexistent"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_poll_success_saves_credentials(self, client: AsyncClient) -> None:
        mock_reg = AsyncMock()
        mock_reg.poll.return_value = _mock_poll_success()
        mock_reg.probe_bot.return_value = {"bot_name": "TestBot", "bot_open_id": "ou_bot_test"}

        session_id = "test_session_001"
        _active_sessions[session_id] = _RegistrationSession(registration=mock_reg, device_code="dc_test")

        with patch("app.api.channels.feishu_register._save_credentials_to_db", new_callable=AsyncMock) as mock_save:
            resp = await client.post(
                "/channels/manage/feishu/qr-register/poll",
                json={"session_id": session_id},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["credentials"]["appId"] == "cli_test_abc"
        assert data["credentials"]["appSecret"] == "secret_test_xyz"
        mock_save.assert_called_once()
        assert session_id not in _active_sessions

    @pytest.mark.asyncio
    async def test_poll_pending_keeps_session(self, client: AsyncClient) -> None:
        mock_reg = AsyncMock()
        mock_reg.poll.return_value = _mock_poll_pending()

        session_id = "test_session_002"
        _active_sessions[session_id] = _RegistrationSession(registration=mock_reg, device_code="dc_test")

        resp = await client.post(
            "/channels/manage/feishu/qr-register/poll",
            json={"session_id": session_id},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["credentials"] is None
        assert session_id in _active_sessions

    @pytest.mark.asyncio
    async def test_poll_denied_removes_session(self, client: AsyncClient) -> None:
        mock_reg = AsyncMock()
        mock_reg.poll.return_value = _mock_poll_denied()

        session_id = "test_session_003"
        _active_sessions[session_id] = _RegistrationSession(registration=mock_reg, device_code="dc_test")

        resp = await client.post(
            "/channels/manage/feishu/qr-register/poll",
            json={"session_id": session_id},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "denied"
        assert session_id not in _active_sessions

    @pytest.mark.asyncio
    async def test_poll_expired_removes_session(self, client: AsyncClient) -> None:
        mock_reg = AsyncMock()
        mock_reg.poll.return_value = _mock_poll_expired()

        session_id = "test_session_004"
        _active_sessions[session_id] = _RegistrationSession(registration=mock_reg, device_code="dc_test")

        resp = await client.post(
            "/channels/manage/feishu/qr-register/poll",
            json={"session_id": session_id},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "expired"
        assert session_id not in _active_sessions


class TestSessionCleanup:
    def test_cleanup_expired_sessions(self) -> None:
        import time

        mock_reg = AsyncMock()

        session = _RegistrationSession(registration=mock_reg, device_code="dc_old")
        session.created_at = time.monotonic() - _SESSION_TTL_S - 10

        _active_sessions["old_session"] = session
        _active_sessions["new_session"] = _RegistrationSession(registration=mock_reg, device_code="dc_new")

        _cleanup_expired_sessions()

        assert "old_session" not in _active_sessions
        assert "new_session" in _active_sessions

    def test_cleanup_empty_sessions(self) -> None:
        _cleanup_expired_sessions()
        assert len(_active_sessions) == 0
