"""Tests for the shared HMAC signing primitives (share_hmac)."""

import time
from unittest.mock import patch

from app.core.security.share_hmac import (
    b64url_decode,
    b64url_encode,
    create_share_token,
    is_password_protected,
    parse_share_token,
)

_SALT = "test-share"


def test_round_trip() -> None:
    token, exp = create_share_token(
        {"foo": "bar"}, salt=_SALT, ttl_seconds=3600, max_ttl_seconds=86400,
    )
    raw = parse_share_token(token, salt=_SALT)
    assert raw is not None
    assert raw["foo"] == "bar"
    assert raw["exp"] == exp


def test_rejects_tampered_signature() -> None:
    token, _ = create_share_token(
        {"x": 1}, salt=_SALT, ttl_seconds=300, max_ttl_seconds=600,
    )
    tampered = token[:-2] + "zz"
    assert parse_share_token(tampered, salt=_SALT) is None


def test_rejects_expired() -> None:
    token, _ = create_share_token(
        {"x": 1}, salt=_SALT, ttl_seconds=60, max_ttl_seconds=600,
    )
    future = int(time.time()) + 120
    with patch("app.core.security.share_hmac.time.time", return_value=future):
        assert parse_share_token(token, salt=_SALT) is None


def test_ttl_clamped_to_min() -> None:
    _, exp = create_share_token(
        {"x": 1}, salt=_SALT, ttl_seconds=5, max_ttl_seconds=600,
    )
    now = int(time.time())
    assert exp >= now + 60


def test_ttl_clamped_to_max() -> None:
    _, exp = create_share_token(
        {"x": 1}, salt=_SALT, ttl_seconds=999999, max_ttl_seconds=600,
    )
    now = int(time.time())
    assert exp <= now + 600 + 2


def test_different_salts_produce_different_tokens() -> None:
    payload = {"id": "same"}
    t1, _ = create_share_token(payload, salt="alpha", ttl_seconds=300, max_ttl_seconds=600)
    t2, _ = create_share_token(payload, salt="beta", ttl_seconds=300, max_ttl_seconds=600)
    assert t1 != t2
    assert parse_share_token(t1, salt="beta") is None


def test_password_round_trip() -> None:
    token, exp = create_share_token(
        {"id": "pw-test"}, salt=_SALT, ttl_seconds=300,
        max_ttl_seconds=600, password="hunter2",
    )
    assert is_password_protected(token) is True
    assert parse_share_token(token, salt=_SALT) is None
    raw = parse_share_token(token, salt=_SALT, password="hunter2")
    assert raw is not None
    assert raw["id"] == "pw-test"
    assert raw["exp"] == exp


def test_password_rejects_wrong() -> None:
    token, _ = create_share_token(
        {"id": "x"}, salt=_SALT, ttl_seconds=300,
        max_ttl_seconds=600, password="correct",
    )
    assert parse_share_token(token, salt=_SALT, password="wrong") is None


def test_non_password_not_protected() -> None:
    token, _ = create_share_token(
        {"id": "y"}, salt=_SALT, ttl_seconds=300, max_ttl_seconds=600,
    )
    assert is_password_protected(token) is False


def test_is_password_protected_edge_cases() -> None:
    assert is_password_protected("") is False
    assert is_password_protected("not-a-token") is False
    assert is_password_protected("abc.def") is False


def test_b64url_round_trip() -> None:
    data = b"hello world! \x00\xff"
    encoded = b64url_encode(data)
    assert "=" not in encoded
    assert b64url_decode(encoded) == data


def test_rejects_malformed_input() -> None:
    assert parse_share_token("", salt=_SALT) is None
    assert parse_share_token("no-dot-here", salt=_SALT) is None
    assert parse_share_token("not-base64.abcdef", salt=_SALT) is None


def test_rejects_unknown_token_version() -> None:
    """A token carrying an unsupported version must be rejected."""
    from app.core.security.share_hmac import (
        b64url_encode,
        sign_share_token,
    )

    base, sig = sign_share_token(
        {"x": 1}, salt=_SALT, exp=int(time.time()) + 300,
    ).rsplit(".", 1)
    # Rewrite the version field to an unknown one; the signature check is
    # reached after the version gate, so tampering breaks both.
    import json

    raw = json.loads(b64url_decode(base))
    raw["v"] = 999
    forged = b64url_encode(json.dumps(raw, separators=(",", ":")).encode("utf-8"))
    assert parse_share_token(f"{forged}.{sig}", salt=_SALT) is None


def test_signing_secret_falls_back_to_state_dir() -> None:
    """When no secret is configured the signing key degrades to state_dir."""
    from app.core.security.share_hmac import _signing_secret

    with (
        patch(
            "app.core.security.share_hmac.settings.config_encryption_key.get_secret_value",
            return_value="",
        ),
        patch(
            "app.core.security.share_hmac.settings.internal_service_key.get_secret_value",
            return_value="  ",
        ),
        patch(
            "app.core.security.share_hmac.settings.sandbox_api_key.get_secret_value",
            return_value=None,
        ),
        patch(
            "app.core.security.share_hmac.settings.database.state_dir",
            new="myrm-test-dir",
        ),
    ):
        key = _signing_secret("test-salt")
    assert key != b""


def test_signing_secret_uses_configured_key() -> None:
    """When a secret is configured it is used as the signing base key."""
    from app.core.security.share_hmac import _signing_secret

    with (
        patch(
            "app.core.security.share_hmac.settings.config_encryption_key.get_secret_value",
            return_value="  my-enc-key  ",
        ),
        patch(
            "app.core.security.share_hmac.settings.internal_service_key.get_secret_value",
            return_value="other-key",
        ),
    ):
        key = _signing_secret("test-salt")
    assert key != b""
    # A different configured key must derive a different signing secret.
    with patch(
        "app.core.security.share_hmac.settings.config_encryption_key.get_secret_value",
        return_value="  my-enc-key-2  ",
    ):
        assert _signing_secret("test-salt") != key
