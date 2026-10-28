"""Tests for visitor language negotiation on the public share pages."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.security.share.share_locale import resolve_share_lang


def _request(accept_language: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if accept_language is not None:
        headers.append((b"accept-language", accept_language.encode()))
    return Request(scope={"type": "http", "method": "GET", "path": "/", "headers": headers})


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("*", "en"),
        ("en", "en"),
        ("en-US,en;q=0.9", "en"),
        ("zh", "zh"),
        ("zh-CN,zh;q=0.9,en;q=0.8", "zh"),
        ("zh-TW", "zh"),
        ("zh-Hans-CN", "zh"),
        ("ZH-cn", "zh"),
        ("en-US,zh;q=0.9", "en"),
        ("en;q=0.5,zh;q=0.9", "zh"),
        ("fr-FR,zh;q=0.8", "zh"),
        ("fr-FR,de;q=0.8", "en"),
        ("zh;q=0,en", "en"),
        ("en;q=0,zh", "zh"),
        ("zh;q=abc,en", "en"),
        ("zh ; q = 0.4 , en;q=0.3", "zh"),
        (",,;q=0.5,zh", "zh"),
    ],
)
def test_the_best_supported_language_wins(header: str | None, expected: str) -> None:
    assert resolve_share_lang(_request(header)) == expected
