"""Tests for what refresh_oauth_token remembers: rejected tokens, cooldowns, shielding, expiry."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.agent import oauth_refresher
from app.services.agent.oauth_refresher import is_refresh_rejected, refresh_oauth_token
from tests.support.jwt_tokens import make_jwt

_ISSUER = "test_issuer"
_TOKEN_URL = "https://example.com/token"
_BUS_TARGET = "app.services.event.app_event_bus.get_event_bus"


class _SessionCtx:
    def __init__(self, session: MagicMock) -> None:
        self._session = session

    async def __aenter__(self) -> MagicMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


def _session_for(cred: dict[str, object]) -> MagicMock:
    row = MagicMock()
    row.config_value = {_ISSUER: cred}
    row.is_encrypted = False
    result = MagicMock()
    result.scalars.return_value.first.return_value = row
    session = AsyncMock()
    session.execute.return_value = result
    return MagicMock(return_value=_SessionCtx(session))


def _response(status: int, body: object | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = str(body)
    if body is None:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body
    return response


def _expired(refresh_token: str = "rt_1") -> dict[str, object]:
    return {
        "token": "old-access",
        "refresh_token": refresh_token,
        "token_url": _TOKEN_URL,
        "user_id": "u1",
        "expires_at": time.time() - 100,
    }


@contextmanager
def _refresh_env(cred: dict[str, object], post: AsyncMock) -> Iterator[tuple[MagicMock, AsyncMock]]:
    """Patch storage, HTTP and the event bus; yield (bus, merge-write-back mock)."""
    bus = MagicMock()
    merge = AsyncMock()
    with (
        patch.object(oauth_refresher, "get_session", _session_for(cred)),
        patch.object(oauth_refresher, "get_encryption_service"),
        patch.object(oauth_refresher, "_merge_refreshed_credential", merge),
        patch("httpx.AsyncClient.post", post),
        patch(_BUS_TARGET, return_value=bus),
    ):
        yield bus, merge


def _published_reasons(bus: MagicMock) -> list[str]:
    return [call.args[0].data["reason"] for call in bus.publish.call_args_list]


class TestRejectedRefreshToken:
    @pytest.mark.asyncio
    async def test_is_not_retried_until_the_user_signs_in_again(self) -> None:
        post = AsyncMock(return_value=_response(400, {"error": "invalid_grant", "error_description": "revoked"}))

        with _refresh_env(_expired("rt_dead"), post) as (bus, _):
            assert await refresh_oauth_token(_ISSUER) is None
            assert await refresh_oauth_token(_ISSUER) is None

        assert post.await_count == 1
        assert _published_reasons(bus) == ["revoked"]

        with _refresh_env(_expired("rt_after_relogin"), post):
            await refresh_oauth_token(_ISSUER)

        assert post.await_count == 2

    @pytest.mark.asyncio
    async def test_keeps_notifying_without_spending_another_attempt(self) -> None:
        post = AsyncMock(return_value=_response(401, {"error": "invalid_grant"}))

        with _refresh_env(_expired(), post) as (bus, _):
            await refresh_oauth_token(_ISSUER)
            oauth_refresher._reauth_emitted_at.clear()
            await refresh_oauth_token(_ISSUER)

        assert post.await_count == 1
        assert _published_reasons(bus) == ["invalid_grant", "token_expired"]

    @pytest.mark.asyncio
    async def test_a_fresh_stored_token_bypasses_the_rejection(self) -> None:
        post = AsyncMock(return_value=_response(400, {"error": "invalid_grant"}))
        with _refresh_env(_expired(), post):
            await refresh_oauth_token(_ISSUER)

        signed_in_again = {**_expired(), "token": "new-access", "expires_at": time.time() + 3600}
        with _refresh_env(signed_in_again, post):
            result = await refresh_oauth_token(_ISSUER)

        assert result is not None
        assert result.token == "new-access"
        assert post.await_count == 1


class TestTransientFailure:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [429, 503, 403, 407])
    async def test_cools_down_without_notifying_then_retries(self, status: int) -> None:
        post = AsyncMock(return_value=_response(status))

        with _refresh_env(_expired(), post) as (bus, _):
            assert await refresh_oauth_token(_ISSUER) is None
            assert await refresh_oauth_token(_ISSUER) is None
            assert post.await_count == 1

            oauth_refresher._retry_not_before[_ISSUER] = time.monotonic() - 1
            await refresh_oauth_token(_ISSUER)

        assert post.await_count == 2
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_network_error_cools_down(self) -> None:
        post = AsyncMock(side_effect=httpx.ConnectError("offline"))

        with _refresh_env(_expired(), post) as (bus, _):
            assert await refresh_oauth_token(_ISSUER) is None
            assert await refresh_oauth_token(_ISSUER) is None

        assert post.await_count == 1
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_response_without_access_token_cools_down(self) -> None:
        post = AsyncMock(return_value=_response(200, {"refresh_token": "rotated"}))

        with _refresh_env(_expired(), post) as (_, merge):
            assert await refresh_oauth_token(_ISSUER) is None
            assert await refresh_oauth_token(_ISSUER) is None

        assert post.await_count == 1
        merge.assert_not_awaited()


class TestRejectionIsVisibleWithoutRefreshing:
    @pytest.mark.asyncio
    async def test_reports_only_the_rejected_refresh_token(self) -> None:
        post = AsyncMock(return_value=_response(400, {"error": "invalid_grant"}))

        assert is_refresh_rejected(_ISSUER, _expired("rt_dead")) is False

        with _refresh_env(_expired("rt_dead"), post):
            await refresh_oauth_token(_ISSUER)

        assert is_refresh_rejected(_ISSUER, _expired("rt_dead")) is True
        assert is_refresh_rejected(_ISSUER, _expired("rt_after_relogin")) is False
        assert is_refresh_rejected("another_issuer", _expired("rt_dead")) is False
        assert is_refresh_rejected(_ISSUER, {"token": "t"}) is False
        assert post.await_count == 1

    @pytest.mark.asyncio
    async def test_a_tier_gate_is_not_reported_as_a_rejection(self) -> None:
        gate = {"code": "forbidden", "error": "This account is not authorized for API access."}
        post = AsyncMock(return_value=_response(403, gate))

        with _refresh_env(_expired("rt_valid"), post) as (bus, _):
            assert await refresh_oauth_token(_ISSUER) is None

        assert is_refresh_rejected(_ISSUER, _expired("rt_valid")) is False
        bus.publish.assert_not_called()


class TestSuccessfulRefresh:
    @pytest.mark.asyncio
    async def test_expiry_comes_from_the_token_and_failure_memory_is_cleared(self) -> None:
        exp = time.time() + 900
        access = make_jwt({"exp": exp})
        post = AsyncMock(return_value=_response(200, {"access_token": access, "refresh_token": "rt_rotated"}))
        oauth_refresher._retry_not_before[_ISSUER] = time.monotonic() - 1
        oauth_refresher._rejected_refresh_tokens[_ISSUER] = "fingerprint-of-an-older-token"

        with _refresh_env(_expired(), post) as (_, merge):
            result = await refresh_oauth_token(_ISSUER)

        assert result is not None
        assert result.token == access
        assert result.expires_at == exp
        updated = merge.await_args.kwargs["updated_cred"]
        assert updated["refresh_token"] == "rt_rotated"
        assert updated["expires_at"] == exp
        assert _ISSUER not in oauth_refresher._retry_not_before
        assert _ISSUER not in oauth_refresher._rejected_refresh_tokens

    @pytest.mark.asyncio
    async def test_overlong_stored_expiry_does_not_hide_an_expired_token(self) -> None:
        """A persisted expires_at 6 h ahead must not make an already-expired JWT look freshly refreshed."""
        cred = {**_expired(), "token": make_jwt({"exp": time.time() - 30}), "expires_at": time.time() + 21600}
        post = AsyncMock(return_value=_response(200, {"access_token": "new-access", "expires_in": 3600}))

        with _refresh_env(cred, post):
            result = await refresh_oauth_token(_ISSUER)

        assert post.await_count == 1
        assert result is not None
        assert result.token == "new-access"


class TestCancellationShield:
    @pytest.mark.asyncio
    async def test_cancelled_caller_does_not_abandon_the_token_exchange(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        persisted = asyncio.Event()

        async def slow_post(*args: object, **kwargs: object) -> MagicMock:
            started.set()
            await release.wait()
            return _response(200, {"access_token": "rotated-access", "refresh_token": "rt_rotated", "expires_in": 3600})

        post = AsyncMock(side_effect=slow_post)

        with _refresh_env(_expired(), post) as (_, merge):
            merge.side_effect = lambda **kwargs: persisted.set()
            caller = asyncio.create_task(refresh_oauth_token(_ISSUER))
            await asyncio.wait_for(started.wait(), timeout=2)

            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller

            release.set()
            await asyncio.wait_for(persisted.wait(), timeout=2)

        merge.assert_awaited_once()
        assert merge.await_args.kwargs["updated_cred"]["refresh_token"] == "rt_rotated"
