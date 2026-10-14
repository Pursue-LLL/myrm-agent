"""Tests for the pure OAuth token-lifetime and refresh-failure policy."""

from __future__ import annotations

import pytest

from app.services.agent.oauth_token_policy import (
    DEFAULT_TOKEN_TTL_S,
    TOKEN_REFRESH_LEAD_S,
    classify_refresh_failure,
    credential_expiry,
    is_refresh_due,
    jwt_expiry,
    refresh_token_fingerprint,
    resolve_expires_at,
)
from tests.support.jwt_tokens import encode_segment, make_jwt

NOW = 1_800_000_000.0


class TestJwtExpiry:
    def test_reads_exp_claim(self) -> None:
        assert jwt_expiry(make_jwt({"exp": NOW + 900})) == NOW + 900

    @pytest.mark.parametrize(
        "token",
        [
            "opaque-token-without-dots",
            "only.two",
            "a.b.c.d",
            "header.!!not-base64!!.sig",
            f"h.{encode_segment('a string payload')}.s",
            f"h.{encode_segment({'sub': 'no-exp'})}.s",
            f"h.{encode_segment({'exp': 'soon'})}.s",
            f"h.{encode_segment({'exp': True})}.s",
            f"h.{encode_segment({'exp': 0})}.s",
            f"h.{encode_segment({'exp': -5})}.s",
            None,
            12345,
        ],
    )
    def test_unusable_tokens_yield_none(self, token: object) -> None:
        assert jwt_expiry(token) is None


class TestResolveExpiresAt:
    def test_short_lived_jwt_beats_generous_expires_in(self) -> None:
        token = make_jwt({"exp": NOW + 900})

        assert resolve_expires_at(token, 21600, now=NOW) == NOW + 900

    def test_shorter_expires_in_beats_long_lived_jwt(self) -> None:
        token = make_jwt({"exp": NOW + 86400})

        assert resolve_expires_at(token, 600, now=NOW) == NOW + 600

    def test_opaque_token_uses_expires_in_including_numeric_strings(self) -> None:
        assert resolve_expires_at("ya29.opaque", 1800, now=NOW) == NOW + 1800
        assert resolve_expires_at("ya29.opaque", "1800", now=NOW) == NOW + 1800

    @pytest.mark.parametrize("expires_in", [None, "", "soon", 0, -30, float("inf"), float("nan"), True])
    def test_unstated_or_invalid_lifetime_falls_back_to_default(self, expires_in: object) -> None:
        assert resolve_expires_at("opaque", expires_in, now=NOW) == NOW + DEFAULT_TOKEN_TTL_S

    def test_jwt_alone_is_enough_when_expires_in_is_absent(self) -> None:
        assert resolve_expires_at(make_jwt({"exp": NOW + 900}), None, now=NOW) == NOW + 900


class TestCredentialExpiry:
    def test_overlong_stored_expiry_is_capped_by_the_token_itself(self) -> None:
        credential = {"token": make_jwt({"exp": NOW + 900}), "expires_at": NOW + 21600}

        assert credential_expiry(credential) == NOW + 900

    def test_stored_expiry_for_opaque_token(self) -> None:
        assert credential_expiry({"token": "opaque", "expires_at": NOW + 60}) == NOW + 60

    def test_jwt_alone(self) -> None:
        assert credential_expiry({"token": make_jwt({"exp": NOW + 60})}) == NOW + 60

    def test_unknown_expiry(self) -> None:
        assert credential_expiry({"token": "opaque"}) is None


class TestIsRefreshDue:
    def test_due_inside_the_lead_window_and_after_expiry(self) -> None:
        assert is_refresh_due({"token": "t", "expires_at": NOW + TOKEN_REFRESH_LEAD_S}, now=NOW) is True
        assert is_refresh_due({"token": "t", "expires_at": NOW - 10}, now=NOW) is True

    def test_not_due_outside_the_lead_window(self) -> None:
        assert is_refresh_due({"token": "t", "expires_at": NOW + TOKEN_REFRESH_LEAD_S + 1}, now=NOW) is False

    def test_unknown_expiry_is_not_due(self) -> None:
        assert is_refresh_due({"token": "opaque"}, now=NOW) is False

    def test_stale_persisted_expiry_is_caught_through_the_jwt(self) -> None:
        credential = {"token": make_jwt({"exp": NOW - 60}), "expires_at": NOW + 21600}

        assert is_refresh_due(credential, now=NOW) is True


class TestClassifyRefreshFailure:
    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (400, {"error": "invalid_grant"}),
            (401, {"error": "invalid_client"}),
            (401, None),
            (403, {"error": "access_denied"}),
            (400, "not-json-object"),
        ],
    )
    def test_rejections_are_terminal(self, status: int, body: object) -> None:
        assert classify_refresh_failure(status, body) == "terminal"

    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (408, None),
            (425, None),
            (429, {"error": "rate_limited"}),
            (500, None),
            (503, {"error": "invalid_grant"}),
            (302, None),
            (400, {"error": "temporarily_unavailable"}),
            (400, {"error": "server_error"}),
            (400, {"error": "slow_down"}),
        ],
    )
    def test_outages_and_rate_limits_are_transient(self, status: int, body: object) -> None:
        assert classify_refresh_failure(status, body) == "transient"


class TestRefreshTokenFingerprint:
    def test_stable_distinct_and_not_the_token(self) -> None:
        first = refresh_token_fingerprint("refresh-token-a")

        assert first == refresh_token_fingerprint("refresh-token-a")
        assert first != refresh_token_fingerprint("refresh-token-b")
        assert "refresh-token-a" not in first
        assert len(first) == 16
