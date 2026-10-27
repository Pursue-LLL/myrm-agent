"""Tests for the share password-gate lockout (per share token and client)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from starlette.requests import Request

from app.core.security.share import share_attempt_guard
from app.core.security.share.share_attempt_guard import (
    password_lockout_response,
    record_password_failure,
    record_password_success,
)

_TOKEN = "token-a"


def _request(host: str | None = "10.0.0.1") -> Request:
    client = SimpleNamespace(host=host) if host is not None else None
    return cast(Request, SimpleNamespace(client=client))


def _fail(token: str, host: str | None, times: int) -> None:
    for _ in range(times):
        record_password_failure(_request(host), token)


@pytest.fixture(autouse=True)
def _fresh_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.security.auth.failed_attempt_guard import FailedAttemptGuard

    monkeypatch.setattr(share_attempt_guard, "_guard", FailedAttemptGuard())


def test_no_lockout_before_the_failure_limit() -> None:
    _fail(_TOKEN, "10.0.0.1", 4)
    assert password_lockout_response(_request(), _TOKEN) is None


def test_lockout_page_is_a_429_with_retry_after_and_a_disabled_form() -> None:
    _fail(_TOKEN, "10.0.0.1", 5)

    response = password_lockout_response(_request(), _TOKEN)

    assert response is not None
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    body = bytes(response.body).decode()
    assert "Too many incorrect attempts" in body
    assert "autofocus disabled/>" in body
    assert 'type="submit" disabled>' in body


def test_lockout_is_scoped_to_token_and_client() -> None:
    _fail(_TOKEN, "10.0.0.1", 5)

    assert password_lockout_response(_request("10.0.0.1"), _TOKEN) is not None
    assert password_lockout_response(_request("10.0.0.2"), _TOKEN) is None
    assert password_lockout_response(_request("10.0.0.1"), "token-b") is None


def test_success_clears_the_failures() -> None:
    _fail(_TOKEN, "10.0.0.1", 4)
    record_password_success(_request(), _TOKEN)
    _fail(_TOKEN, "10.0.0.1", 4)

    assert password_lockout_response(_request(), _TOKEN) is None


def test_clients_without_an_address_share_one_bucket() -> None:
    _fail(_TOKEN, None, 5)

    assert password_lockout_response(_request(None), _TOKEN) is not None
    assert password_lockout_response(_request("10.0.0.1"), _TOKEN) is None


def test_state_never_holds_the_raw_token() -> None:
    _fail(_TOKEN, "10.0.0.1", 1)

    assert all(_TOKEN not in key for key in share_attempt_guard._guard._failures)
