"""Tests for subscription token custody: load-time renewal, marker swap and the harness hook."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent import provider_oauth_tokens as tokens
from app.services.agent.oauth_token_policy import TOKEN_REFRESH_LEAD_S
from app.services.agent.provider_oauth_tokens import (
    OAUTH_KEY_MARKER,
    PROVIDER_OAUTH_ISSUERS,
    ProviderOAuthUnavailableError,
    freshen_api_key,
    refresh_provider_oauth_credentials,
    resolve_oauth_marker,
)

_MODULE = "app.services.agent.provider_oauth_tokens"
_XAI_BASE_URL = "https://api.x.ai/v1"
_FRONTEND_PROVIDER_TYPES_TS = (
    Path(__file__).resolve().parents[4] / "myrm-agent-frontend" / "src" / "store" / "config" / "providerTypes.ts"
)


def _credential(token: str = "stored-token", *, expires_in: float = 3600, **extra: object) -> dict[str, object]:
    return {
        "token": token,
        "refresh_token": "rt_1",
        "token_url": "https://auth.x.ai/oauth2/token",
        "base_url": _XAI_BASE_URL,
        "expires_at": time.time() + expires_in,
        **extra,
    }


def _due_credential(token: str = "stale-token") -> dict[str, object]:
    return _credential(token, expires_in=TOKEN_REFRESH_LEAD_S - 100)


def _refreshed(token: str = "renewed-token", expires_in: float = 3600) -> SimpleNamespace:
    return SimpleNamespace(token=token, expires_at=time.time() + expires_in)


class TestRegistry:
    def test_xai_is_the_only_subscription_provider(self) -> None:
        assert PROVIDER_OAUTH_ISSUERS == {"xai": "xai"}

    def test_key_marker_matches_the_frontend_placeholder(self) -> None:
        """A drifted literal would send the placeholder to the provider as a real key."""
        source = _FRONTEND_PROVIDER_TYPES_TS.read_text(encoding="utf-8")
        match = re.search(r"OAUTH_AUTH_API_KEY_MARKER\s*=\s*'([^']+)'", source)

        assert match is not None, "OAUTH_AUTH_API_KEY_MARKER missing in the frontend provider types"
        assert match.group(1) == OAUTH_KEY_MARKER


class TestRefreshProviderOAuthCredentials:
    @pytest.mark.asyncio
    async def test_fresh_entry_is_left_alone_and_remembered(self) -> None:
        entry = _credential("fresh-token")
        blob: dict[str, object] = {"xai": entry}

        with patch(f"{_MODULE}.refresh_oauth_token", AsyncMock()) as refresh:
            await refresh_provider_oauth_credentials(blob)

        refresh.assert_not_awaited()
        assert blob["xai"] == entry
        assert "fresh-token" in tokens._issued_tokens

    @pytest.mark.asyncio
    async def test_due_entry_gets_the_renewed_token_in_place(self) -> None:
        blob: dict[str, object] = {"xai": _due_credential()}
        renewed = _refreshed()

        with patch(f"{_MODULE}.refresh_oauth_token", AsyncMock(return_value=renewed)) as refresh:
            await refresh_provider_oauth_credentials(blob)

        refresh.assert_awaited_once_with("xai")
        entry = blob["xai"]
        assert isinstance(entry, dict)
        assert entry["token"] == "renewed-token"
        assert entry["expires_at"] == renewed.expires_at
        assert entry["refresh_token"] == "rt_1"
        assert "renewed-token" in tokens._issued_tokens

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "refresh",
        [
            AsyncMock(return_value=None),
            AsyncMock(side_effect=RuntimeError("storage down")),
        ],
        ids=["no-credential", "raises"],
    )
    async def test_failed_renewal_keeps_the_stored_token(self, refresh: AsyncMock) -> None:
        entry = _due_credential()
        blob: dict[str, object] = {"xai": entry}

        with patch(f"{_MODULE}.refresh_oauth_token", refresh):
            await refresh_provider_oauth_credentials(blob)

        assert blob["xai"] == entry

    @pytest.mark.asyncio
    async def test_slow_renewal_does_not_hold_up_config_loading(self) -> None:
        entry = _due_credential()
        blob: dict[str, object] = {"xai": entry}

        async def slow_refresh(issuer: str) -> SimpleNamespace:
            await asyncio.sleep(5)
            return _refreshed()

        started = time.monotonic()
        with (
            patch(f"{_MODULE}.refresh_oauth_token", slow_refresh),
            patch.object(tokens, "_LOAD_REFRESH_BUDGET_S", 0.05),
        ):
            await refresh_provider_oauth_credentials(blob)

        assert time.monotonic() - started < 2
        assert blob["xai"] == entry

    @pytest.mark.asyncio
    async def test_other_issuers_and_malformed_entries_are_ignored(self) -> None:
        blob: dict[str, object] = {
            "google_workspace": _due_credential("google-token"),
            "xai": {"refresh_token": "rt_only"},
            "unrelated": "not-a-dict",
        }
        before = dict(blob)

        with patch(f"{_MODULE}.refresh_oauth_token", AsyncMock()) as refresh:
            await refresh_provider_oauth_credentials(blob)

        refresh.assert_not_awaited()
        assert blob == before


class TestResolveOAuthMarker:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("api_key", [None, "sk-user-key", "__myrm_local_no_auth__"])
    async def test_other_keys_pass_through_without_touching_storage(self, api_key: str | None) -> None:
        kwargs: dict[str, object] = {"model": "xai/grok-4", "api_key": api_key}

        with patch(f"{_MODULE}._load_stored_credential", AsyncMock()) as load:
            await resolve_oauth_marker(kwargs)

        load.assert_not_awaited()
        assert kwargs["api_key"] == api_key

    @pytest.mark.asyncio
    @pytest.mark.parametrize("base_url", [None, "", _XAI_BASE_URL, "https://API.X.AI/v1/"])
    async def test_marker_becomes_the_stored_token_for_the_issuing_host(self, base_url: str | None) -> None:
        kwargs: dict[str, object] = {"model": "xai/grok-4", "api_key": OAUTH_KEY_MARKER, "base_url": base_url}

        with patch(f"{_MODULE}._load_stored_credential", AsyncMock(return_value=_credential("stored-token"))):
            await resolve_oauth_marker(kwargs)

        assert kwargs["api_key"] == "stored-token"
        assert "stored-token" in tokens._issued_tokens

    @pytest.mark.asyncio
    async def test_due_token_is_renewed_before_the_swap(self) -> None:
        kwargs: dict[str, object] = {"model": "xai/grok-4", "api_key": OAUTH_KEY_MARKER}

        with (
            patch(f"{_MODULE}._load_stored_credential", AsyncMock(return_value=_due_credential())),
            patch(f"{_MODULE}.refresh_oauth_token", AsyncMock(return_value=_refreshed("renewed-token"))),
        ):
            await resolve_oauth_marker(kwargs)

        assert kwargs["api_key"] == "renewed-token"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "base_url",
        [
            "https://evil.example/v1",
            "http://api.x.ai/v1",
            "https://api.x.ai.evil.example/v1",
            "https://api.x.ai@evil.example/v1",
            "ftp://api.x.ai/v1",
        ],
    )
    async def test_token_is_never_sent_to_another_host(self, base_url: str) -> None:
        kwargs: dict[str, object] = {"model": "xai/grok-4", "api_key": OAUTH_KEY_MARKER, "base_url": base_url}

        with patch(f"{_MODULE}._load_stored_credential", AsyncMock(return_value=_credential())):
            with pytest.raises(ProviderOAuthUnavailableError):
                await resolve_oauth_marker(kwargs)

        assert kwargs["api_key"] == OAUTH_KEY_MARKER

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("model", "stored"),
        [
            ("openai/gpt-4o", _credential()),
            ("grok-4", _credential()),
            ("xai/grok-4", None),
            ("xai/grok-4", {"refresh_token": "rt_only", "base_url": _XAI_BASE_URL}),
            ("xai/grok-4", {"token": "t"}),
        ],
        ids=["other-provider", "no-provider-prefix", "disconnected", "no-token", "no-issuing-host"],
    )
    async def test_unavailable_subscription_is_reported(self, model: str, stored: dict[str, object] | None) -> None:
        kwargs: dict[str, object] = {"model": model, "api_key": OAUTH_KEY_MARKER}

        with patch(f"{_MODULE}._load_stored_credential", AsyncMock(return_value=stored)):
            with pytest.raises(ProviderOAuthUnavailableError):
                await resolve_oauth_marker(kwargs)

        assert kwargs["api_key"] == OAUTH_KEY_MARKER


class TestFreshenApiKey:
    @pytest.mark.asyncio
    async def test_keys_it_never_issued_cost_nothing(self) -> None:
        with patch(f"{_MODULE}._load_stored_credential", AsyncMock()) as load:
            assert await freshen_api_key("sk-user-key") is None

        load.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unexpired_token_is_not_touched(self) -> None:
        tokens._remember("xai", _credential("fresh-token"))

        with patch(f"{_MODULE}._load_stored_credential", AsyncMock()) as load:
            assert await freshen_api_key("fresh-token") is None

        load.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_token_without_known_expiry_is_trusted(self) -> None:
        tokens._remember("xai", {"token": "opaque-token"})

        with patch(f"{_MODULE}._load_stored_credential", AsyncMock()) as load:
            assert await freshen_api_key("opaque-token") is None

        load.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expiring_token_is_replaced_by_the_renewed_one(self) -> None:
        tokens._remember("xai", _due_credential("stale-token"))

        with (
            patch(f"{_MODULE}._load_stored_credential", AsyncMock(return_value=_due_credential("stale-token"))),
            patch(f"{_MODULE}.refresh_oauth_token", AsyncMock(return_value=_refreshed("renewed-token"))) as refresh,
        ):
            assert await freshen_api_key("stale-token") == "renewed-token"
            refresh.assert_awaited_once_with("xai")

            # The renewed token is itself tracked: while fresh it needs nothing further.
            assert await freshen_api_key("renewed-token") is None

    @pytest.mark.asyncio
    async def test_token_rotated_by_another_path_is_adopted_without_a_refresh(self) -> None:
        tokens._remember("xai", _due_credential("stale-token"))

        with (
            patch(f"{_MODULE}._load_stored_credential", AsyncMock(return_value=_credential("rotated-elsewhere"))),
            patch(f"{_MODULE}.refresh_oauth_token", AsyncMock()) as refresh,
        ):
            assert await freshen_api_key("stale-token") == "rotated-elsewhere"

        refresh.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("stored", "refresh"),
        [
            (None, AsyncMock()),
            (_due_credential("stale-token"), AsyncMock(return_value=None)),
            (_due_credential("stale-token"), AsyncMock(side_effect=RuntimeError("down"))),
        ],
        ids=["disconnected", "refresh-unavailable", "refresh-raises"],
    )
    async def test_when_no_better_token_exists_the_key_is_kept(
        self, stored: dict[str, object] | None, refresh: AsyncMock
    ) -> None:
        tokens._remember("xai", _due_credential("stale-token"))

        with (
            patch(f"{_MODULE}._load_stored_credential", AsyncMock(return_value=stored)),
            patch(f"{_MODULE}.refresh_oauth_token", refresh),
        ):
            assert await freshen_api_key("stale-token") is None


class TestIssuedTokenBookkeeping:
    def test_memory_is_bounded_and_evicts_the_oldest(self) -> None:
        for index in range(tokens._MAX_ISSUED_TOKENS + 5):
            tokens._remember("xai", _credential(f"token-{index}"))

        assert len(tokens._issued_tokens) == tokens._MAX_ISSUED_TOKENS
        assert "token-0" not in tokens._issued_tokens
        assert f"token-{tokens._MAX_ISSUED_TOKENS + 4}" in tokens._issued_tokens

    def test_entries_without_a_token_are_not_remembered(self) -> None:
        tokens._remember("xai", {"refresh_token": "rt_only"})
        tokens._remember("xai", {"token": ""})

        assert not tokens._issued_tokens


class TestLoadStoredCredential:
    @staticmethod
    def _session(row: MagicMock | None) -> MagicMock:
        class _Ctx:
            async def __aenter__(self) -> MagicMock:
                return MagicMock()

            async def __aexit__(self, *args: object) -> None:
                return None

        return MagicMock(return_value=_Ctx())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("row_value", "expected"),
        [
            (None, None),
            ({"google_workspace": {"token": "g"}}, None),
            ({"xai": "not-a-dict"}, None),
            ({"xai": {"token": "stored-token"}}, {"token": "stored-token"}),
        ],
        ids=["no-row", "issuer-missing", "malformed", "present"],
    )
    async def test_reads_the_issuer_entry(self, row_value: dict[str, object] | None, expected: dict[str, object] | None) -> None:
        row = None if row_value is None else MagicMock(config_value=row_value, is_encrypted=False)

        with (
            patch(f"{_MODULE}.get_session", self._session(row)),
            patch(f"{_MODULE}.load_oauth_credentials_row", AsyncMock(return_value=row)),
        ):
            assert await tokens._load_stored_credential("xai") == expected
