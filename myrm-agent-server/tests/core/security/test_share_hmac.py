"""Tests for the shared HMAC signing primitives (share_hmac)."""

import hashlib
import hmac
import time
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.security.share.share_hmac import (
    b64url_decode,
    b64url_encode,
    create_share_token,
    is_password_protected,
    parse_share_token,
)

_SALT = "test-share"


def test_round_trip() -> None:
    token, exp = create_share_token(
        {"foo": "bar"},
        salt=_SALT,
        ttl_seconds=3600,
        max_ttl_seconds=86400,
    )
    raw = parse_share_token(token, salt=_SALT)
    assert raw is not None
    assert raw["foo"] == "bar"
    assert raw["exp"] == exp


def test_rejects_tampered_signature() -> None:
    token, _ = create_share_token(
        {"x": 1},
        salt=_SALT,
        ttl_seconds=300,
        max_ttl_seconds=600,
    )
    tampered = token[:-2] + "zz"
    assert parse_share_token(tampered, salt=_SALT) is None


def test_rejects_expired() -> None:
    token, _ = create_share_token(
        {"x": 1},
        salt=_SALT,
        ttl_seconds=60,
        max_ttl_seconds=600,
    )
    future = int(time.time()) + 120
    with patch("app.core.security.share.share_hmac.time.time", return_value=future):
        assert parse_share_token(token, salt=_SALT) is None


def test_ttl_clamped_to_min() -> None:
    _, exp = create_share_token(
        {"x": 1},
        salt=_SALT,
        ttl_seconds=5,
        max_ttl_seconds=600,
    )
    now = int(time.time())
    assert exp >= now + 60


def test_ttl_clamped_to_max() -> None:
    _, exp = create_share_token(
        {"x": 1},
        salt=_SALT,
        ttl_seconds=999999,
        max_ttl_seconds=600,
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
        {"id": "pw-test"},
        salt=_SALT,
        ttl_seconds=300,
        max_ttl_seconds=600,
        password="hunter2",
    )
    assert is_password_protected(token) is True
    assert parse_share_token(token, salt=_SALT) is None
    raw = parse_share_token(token, salt=_SALT, password="hunter2")
    assert raw is not None
    assert raw["id"] == "pw-test"
    assert raw["exp"] == exp


def test_password_rejects_wrong() -> None:
    token, _ = create_share_token(
        {"id": "x"},
        salt=_SALT,
        ttl_seconds=300,
        max_ttl_seconds=600,
        password="correct",
    )
    assert parse_share_token(token, salt=_SALT, password="wrong") is None


def test_non_password_not_protected() -> None:
    token, _ = create_share_token(
        {"id": "y"},
        salt=_SALT,
        ttl_seconds=300,
        max_ttl_seconds=600,
    )
    assert is_password_protected(token) is False


def test_is_password_protected_edge_cases() -> None:
    assert is_password_protected("") is False
    assert is_password_protected("not-a-token") is False
    assert is_password_protected("abc.def") is False


@pytest.mark.parametrize("body", [b"[1]", b"1", b'"x"', b"null"])
def test_is_password_protected_rejects_non_object_bodies(body: bytes) -> None:
    """Anonymous callers control the token text; a non-object body must not raise."""
    assert is_password_protected(f"{b64url_encode(body)}.sig") is False


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
    from app.core.security.share.share_hmac import (
        b64url_encode,
        sign_share_token,
    )

    base, sig = sign_share_token(
        {"x": 1},
        salt=_SALT,
        exp=int(time.time()) + 300,
    ).rsplit(".", 1)
    # Rewrite the version field to an unknown one; the signature check is
    # reached after the version gate, so tampering breaks both.
    import json

    raw = json.loads(b64url_decode(base))
    raw["v"] = 999
    forged = b64url_encode(json.dumps(raw, separators=(",", ":")).encode("utf-8"))
    assert parse_share_token(f"{forged}.{sig}", salt=_SALT) is None


_INSTALLATION_KEY = bytes(range(32))


@contextmanager
def _no_configured_secret(installation_key: bytes | None = _INSTALLATION_KEY) -> Iterator[None]:
    """No signing secret in settings; the encryption service holds ``installation_key``."""
    with (
        patch(
            "app.core.security.share.share_hmac.settings.config_encryption_key.get_secret_value",
            return_value="",
        ),
        patch(
            "app.core.security.share.share_hmac.settings.internal_service_key.get_secret_value",
            return_value="  ",
        ),
        patch(
            "app.core.security.share.share_hmac.settings.sandbox_api_key.get_secret_value",
            return_value=None,
        ),
        patch(
            "app.services.config.encryption.get_encryption_service",
            return_value=SimpleNamespace(raw_key=installation_key),
        ),
    ):
        yield


def test_signing_secret_without_configured_key_uses_the_installation_key() -> None:
    """Local installs sign with the persisted per-installation key, not with anything derivable from a path."""
    from app.core.security.share.share_hmac import _signing_secret

    with _no_configured_secret():
        key = _signing_secret("test-salt")
    assert key == hmac.new(_INSTALLATION_KEY, b"test-salt", hashlib.sha256).digest()


def _offline_password_guess(token: str, salt: str, seed: bytes, wordlist: list[str]) -> str | None:
    """What a link holder can do without the server: derive the key from a guessable seed and test each password."""
    body, sig = token.rsplit(".", 1)
    secret = hmac.new(seed, salt.encode(), hashlib.sha256).digest()
    for candidate in wordlist:
        key = hashlib.sha256(secret + hashlib.sha256(candidate.encode()).digest()).digest()
        if hmac.compare_digest(hmac.new(key, body.encode(), hashlib.sha256).hexdigest(), sig):
            return candidate
    return None


def test_password_cannot_be_recovered_offline_from_the_link_and_the_data_dir() -> None:
    """A link holder who guesses the data directory still cannot test passwords against the signature."""
    from app.config.settings import settings

    guessable_seed = hashlib.sha256(settings.database.state_dir.encode("utf-8")).digest()
    wordlist = ["123456", "password", "sunshine", "letmein"]

    with _no_configured_secret():
        token, _ = create_share_token({"id": "pw"}, salt=_SALT, ttl_seconds=300, max_ttl_seconds=600, password="sunshine")
    assert _offline_password_guess(token, _SALT, guessable_seed, wordlist) is None

    # Control: the same attack does succeed when the signing key is the guessable seed, so the check above is not vacuous.
    with _no_configured_secret(installation_key=guessable_seed):
        weak_token, _ = create_share_token({"id": "pw"}, salt=_SALT, ttl_seconds=300, max_ttl_seconds=600, password="sunshine")
    assert _offline_password_guess(weak_token, _SALT, guessable_seed, wordlist) == "sunshine"


def test_signing_secret_fails_closed_without_any_key() -> None:
    from app.core.security.share.share_hmac import _signing_secret

    with _no_configured_secret(installation_key=None), pytest.raises(RuntimeError, match="signing key"):
        _signing_secret("test-salt")


def test_signing_secret_uses_configured_key() -> None:
    """When a secret is configured it is used as the signing base key."""
    from app.core.security.share.share_hmac import _signing_secret

    with (
        patch(
            "app.core.security.share.share_hmac.settings.config_encryption_key.get_secret_value",
            return_value="  my-enc-key  ",
        ),
        patch(
            "app.core.security.share.share_hmac.settings.internal_service_key.get_secret_value",
            return_value="other-key",
        ),
    ):
        key = _signing_secret("test-salt")
    assert key != b""
    # A different configured key must derive a different signing secret.
    with patch(
        "app.core.security.share.share_hmac.settings.config_encryption_key.get_secret_value",
        return_value="  my-enc-key-2  ",
    ):
        assert _signing_secret("test-salt") != key
