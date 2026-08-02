"""Tests for artifact share HMAC tokens (including password gate)."""

import time
from unittest.mock import patch

from app.core.security.share_hmac import is_password_protected
from app.services.artifacts.share_token import (
    create_artifact_share_token,
    is_shareable_artifact,
    is_shareable_artifact_name,
    parse_artifact_share_token,
)


def test_share_token_round_trip() -> None:
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    claims = parse_artifact_share_token(token)
    assert claims is not None
    assert claims.artifact_id == "art-1"
    assert claims.version_id == "ver-1"
    assert claims.exp == exp
    assert claims.password_protected is False


def test_share_token_rejects_tamper() -> None:
    token, _ = create_artifact_share_token("art-1", "ver-1")
    tampered = token[:-2] + "xx"
    assert parse_artifact_share_token(tampered) is None


def test_is_shareable_artifact_name() -> None:
    assert is_shareable_artifact_name("report.html") is True
    assert is_shareable_artifact_name("notes.pdf") is True
    assert is_shareable_artifact_name("app.tsx") is False


def test_is_shareable_artifact_accepts_client_type_without_suffix() -> None:
    assert is_shareable_artifact("Q3报告", artifact_type="document") is True


def test_is_shareable_artifact_rejects_code_type_without_suffix() -> None:
    assert is_shareable_artifact("app", artifact_type="code") is False


def test_share_token_round_trip_with_artifact_type() -> None:
    token, _ = create_artifact_share_token("art-1", "ver-1", artifact_type="document")
    claims = parse_artifact_share_token(token)
    assert claims is not None
    assert claims.artifact_type == "document"


def test_share_token_rejects_expired() -> None:
    token, _ = create_artifact_share_token("art-1", "ver-1", ttl_seconds=60)
    future = int(time.time()) + 120
    with patch("app.core.security.share_hmac.time.time", return_value=future):
        assert parse_artifact_share_token(token) is None


# ── Password gate tests ──────────────────────────────────────────


def test_password_token_round_trip() -> None:
    token, exp = create_artifact_share_token(
        "art-pw", "ver-pw", ttl_seconds=3600, password="s3cret",
    )
    assert is_password_protected(token) is True
    assert parse_artifact_share_token(token) is None
    claims = parse_artifact_share_token(token, password="s3cret")
    assert claims is not None
    assert claims.artifact_id == "art-pw"
    assert claims.password_protected is True
    assert claims.exp == exp


def test_password_token_rejects_wrong_password() -> None:
    token, _ = create_artifact_share_token(
        "art-pw", "ver-pw", password="correct",
    )
    assert parse_artifact_share_token(token, password="wrong") is None


def test_non_password_token_not_protected() -> None:
    token, _ = create_artifact_share_token("art-1", "ver-1")
    assert is_password_protected(token) is False
