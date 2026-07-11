"""Tests for WebPushService — subscription CRUD, broadcast, and error handling."""

from __future__ import annotations

import hashlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock pywebpush before importing service (pywebpush may not be installed in test env)
_mock_pywebpush = MagicMock()
_mock_pywebpush.WebPushException = type("WebPushException", (Exception,), {})
_mock_pywebpush.webpush = MagicMock()
sys.modules.setdefault("pywebpush", _mock_pywebpush)

from app.core.web_push.service import WebPushService, get_web_push_service  # noqa: E402

WebPushException = _mock_pywebpush.WebPushException


def _mock_session_ctx(mock_db: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestHashEndpoint:
    def test_deterministic(self) -> None:
        h1 = WebPushService._hash_endpoint("https://fcm.example.com/push/abc")
        h2 = WebPushService._hash_endpoint("https://fcm.example.com/push/abc")
        assert h1 == h2

    def test_length_is_32(self) -> None:
        h = WebPushService._hash_endpoint("https://example.com")
        assert len(h) == 32

    def test_matches_sha256_prefix(self) -> None:
        endpoint = "https://fcm.example.com/push/abc"
        expected = hashlib.sha256(endpoint.encode()).hexdigest()[:32]
        assert WebPushService._hash_endpoint(endpoint) == expected


class TestEnsureKeys:
    def test_lazy_loads_keys(self) -> None:
        svc = WebPushService()
        assert svc._private_pem is None

        with patch(
            "app.core.web_push.vapid_keys.load_vapid_keys",
            return_value=("MOCK_PEM", "MOCK_PUB"),
        ):
            priv, pub = svc._ensure_keys()

        assert priv == "MOCK_PEM"
        assert pub == "MOCK_PUB"
        assert svc._private_pem == "MOCK_PEM"

    def test_caches_after_first_load(self) -> None:
        svc = WebPushService()
        mock_load = MagicMock(return_value=("PEM", "PUB"))

        with patch("app.core.web_push.vapid_keys.load_vapid_keys", mock_load):
            svc._ensure_keys()
            svc._ensure_keys()

        mock_load.assert_called_once()

    def test_public_key_property(self) -> None:
        svc = WebPushService()
        with patch(
            "app.core.web_push.vapid_keys.load_vapid_keys",
            return_value=("PEM", "PUB_KEY_123"),
        ):
            assert svc.public_key == "PUB_KEY_123"


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_creates_new_subscription(self) -> None:
        svc = WebPushService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with patch(
            "app.database.connection.get_session",
            return_value=_mock_session_ctx(mock_db),
        ):
            endpoint_hash = await svc.subscribe(
                endpoint="https://fcm.example.com/push/a",
                p256dh="p256dh_key",
                auth="auth_key",
                user_agent="TestUA",
            )

        assert len(endpoint_hash) == 32
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_subscription(self) -> None:
        svc = WebPushService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = SimpleNamespace(
            endpoint_hash="existing_hash"
        )
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.connection.get_session",
            return_value=_mock_session_ctx(mock_db),
        ):
            endpoint_hash = await svc.subscribe(
                endpoint="https://fcm.example.com/push/b",
                p256dh="new_p256dh",
                auth="new_auth",
            )

        assert len(endpoint_hash) == 32
        assert mock_db.execute.call_count == 2
        mock_db.commit.assert_called_once()


class TestUnsubscribe:
    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self) -> None:
        svc = WebPushService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.connection.get_session",
            return_value=_mock_session_ctx(mock_db),
        ):
            deleted = await svc.unsubscribe("https://fcm.example.com/push/a")

        assert deleted is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self) -> None:
        svc = WebPushService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.connection.get_session",
            return_value=_mock_session_ctx(mock_db),
        ):
            deleted = await svc.unsubscribe("https://nonexistent.com")

        assert deleted is False


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_subscriptions(self) -> None:
        svc = WebPushService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.database.connection.get_session",
            return_value=_mock_session_ctx(mock_db),
        ):
            count = await svc.broadcast("Test", "Body")

        assert count == 0

    @pytest.mark.asyncio
    async def test_broadcasts_to_all_subscriptions(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        sub1 = SimpleNamespace(
            endpoint="https://e1.com", p256dh="k1", auth="a1", endpoint_hash="h1"
        )
        sub2 = SimpleNamespace(
            endpoint="https://e2.com", p256dh="k2", auth="a2", endpoint_hash="h2"
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sub1, sub2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_send = AsyncMock(return_value=True)
        with (
            patch(
                "app.database.connection.get_session",
                return_value=_mock_session_ctx(mock_db),
            ),
            patch.object(svc, "_send_one", mock_send),
        ):
            count = await svc.broadcast("Title", "Body", "/chat")

        assert count == 2
        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_counts_only_successful_sends(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        sub1 = SimpleNamespace(
            endpoint="https://e1.com", p256dh="k1", auth="a1", endpoint_hash="h1"
        )
        sub2 = SimpleNamespace(
            endpoint="https://e2.com", p256dh="k2", auth="a2", endpoint_hash="h2"
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sub1, sub2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        send_results = [True, False]

        async def side_effect(**_kwargs: object) -> bool:
            return send_results.pop(0)

        with (
            patch(
                "app.database.connection.get_session",
                return_value=_mock_session_ctx(mock_db),
            ),
            patch.object(svc, "_send_one", side_effect=side_effect),
        ):
            count = await svc.broadcast("Title", "Body")

        assert count == 1


class TestSendOne:
    @pytest.mark.asyncio
    async def test_successful_send(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        with patch(
            "asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await svc._send_one(
                endpoint="https://e.com",
                p256dh="k",
                auth="a",
                payload='{"title":"T"}',
                endpoint_hash="h1",
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_removes_gone_subscription_on_410(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        mock_response = MagicMock()
        mock_response.status_code = 410

        exc = WebPushException("gone")
        exc.response = mock_response

        with (
            patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=exc,
            ),
            patch.object(
                svc, "_remove_subscription", new_callable=AsyncMock
            ) as mock_remove,
        ):
            result = await svc._send_one(
                endpoint="https://e.com",
                p256dh="k",
                auth="a",
                payload="{}",
                endpoint_hash="h_gone",
            )

        assert result is False
        mock_remove.assert_called_once_with("h_gone")

    @pytest.mark.asyncio
    async def test_removes_gone_subscription_on_404(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        mock_response = MagicMock()
        mock_response.status_code = 404

        exc = WebPushException("not found")
        exc.response = mock_response

        with (
            patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=exc,
            ),
            patch.object(
                svc, "_remove_subscription", new_callable=AsyncMock
            ) as mock_remove,
        ):
            result = await svc._send_one(
                endpoint="https://e.com",
                p256dh="k",
                auth="a",
                payload="{}",
                endpoint_hash="h_404",
            )

        assert result is False
        mock_remove.assert_called_once_with("h_404")

    @pytest.mark.asyncio
    async def test_returns_false_on_generic_exception(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        with patch(
            "asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=ConnectionError("network"),
        ):
            result = await svc._send_one(
                endpoint="https://e.com",
                p256dh="k",
                auth="a",
                payload="{}",
                endpoint_hash="h_err",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_webpush_exception_without_response(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        exc = WebPushException("server error")

        with patch(
            "asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=exc,
        ):
            result = await svc._send_one(
                endpoint="https://e.com",
                p256dh="k",
                auth="a",
                payload="{}",
                endpoint_hash="h_no_resp",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_webpush_exception_with_non_gone_status(self) -> None:
        svc = WebPushService()
        svc._private_pem = "MOCK_PEM"
        svc._public_key = "MOCK_PUB"

        mock_response = MagicMock()
        mock_response.status_code = 500

        exc = WebPushException("server error")
        exc.response = mock_response

        with (
            patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=exc,
            ),
            patch.object(
                svc, "_remove_subscription", new_callable=AsyncMock
            ) as mock_remove,
        ):
            result = await svc._send_one(
                endpoint="https://e.com",
                p256dh="k",
                auth="a",
                payload="{}",
                endpoint_hash="h_500",
            )

        assert result is False
        mock_remove.assert_not_called()


class TestRemoveSubscription:
    @pytest.mark.asyncio
    async def test_removes_by_hash(self) -> None:
        svc = WebPushService()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.connection.get_session",
            return_value=_mock_session_ctx(mock_db),
        ):
            await svc._remove_subscription("dead_hash")

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self) -> None:
        svc = WebPushService()
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("db error"))

        with patch(
            "app.database.connection.get_session",
            return_value=_mock_session_ctx(mock_db),
        ):
            await svc._remove_subscription("err_hash")


class TestGetWebPushService:
    def test_returns_singleton(self) -> None:
        import app.core.web_push.service as svc_module

        original = svc_module._service
        try:
            svc_module._service = None
            s1 = get_web_push_service()
            s2 = get_web_push_service()
            assert s1 is s2
            assert isinstance(s1, WebPushService)
        finally:
            svc_module._service = original
