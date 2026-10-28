"""Unit tests for the shared share status page module."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.security.share.share_status_page import (
    ShareLinkState,
    render_share_status_html,
    share_not_found,
    wants_html,
)


def _request(accept: str | None, accept_language: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if accept is not None:
        headers.append((b"accept", accept.encode()))
    if accept_language is not None:
        headers.append((b"accept-language", accept_language.encode()))
    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "query_string": b"",
            "root_path": "",
        }
    )


def test_wants_html_matches_text_html_accept() -> None:
    assert wants_html(_request("text/html,application/xhtml+xml")) is True


def test_wants_html_rejects_json_and_missing_accept() -> None:
    assert wants_html(_request("application/json")) is False
    assert wants_html(_request("*/*")) is False
    assert wants_html(_request(None)) is False


def test_render_share_status_html_injects_title_message_and_privacy_meta() -> None:
    html = render_share_status_html(ShareLinkState.REVOKED)
    assert '<html lang="en">' in html
    assert "<title>Link Revoked</title>" in html
    assert "This share link has been revoked by its owner." in html
    assert 'name="robots" content="noindex, nofollow"' in html
    assert "Shared via Myrm Agent" in html


def test_render_share_status_html_has_a_chinese_page() -> None:
    html = render_share_status_html(ShareLinkState.REVOKED, "zh")
    assert '<html lang="zh-CN">' in html
    assert "<title>链接已撤销</title>" in html
    assert "分享者已撤销此链接。" in html
    assert "由 Myrm Agent 分享" in html
    assert "Link Revoked" not in html


@pytest.mark.parametrize("state", list(ShareLinkState))
def test_every_state_has_a_complete_page_in_both_languages(state: ShareLinkState) -> None:
    english = render_share_status_html(state, "en")
    chinese = render_share_status_html(state, "zh")
    assert english != chinese
    for html in (english, chinese):
        assert "%(" not in html
        assert "<h1></h1>" not in html


def test_share_not_found_answers_browser_with_html_404() -> None:
    response = share_not_found(
        _request("text/html"),
        detail="gone",
        state=ShareLinkState.EXPIRED,
        headers={"X-Robots-Tag": "noindex, nofollow"},
    )
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert "This share link has expired or is no longer valid." in bytes(response.body).decode()


def test_share_not_found_follows_the_visitor_language() -> None:
    response = share_not_found(
        _request("text/html", "zh-CN,zh;q=0.9,en;q=0.8"),
        detail="gone",
        state=ShareLinkState.EXPIRED,
        headers={},
    )
    body = bytes(response.body).decode()
    assert "此分享链接已过期或已失效。" in body
    assert "has expired" not in body


def test_share_not_found_raises_english_json_404_for_api_clients_whatever_their_language() -> None:
    for accept in ("application/json", None):
        with pytest.raises(HTTPException) as exc_info:
            share_not_found(
                _request(accept, "zh-CN"),
                detail="gone",
                state=ShareLinkState.EXPIRED,
                headers={"X-Robots-Tag": "noindex, nofollow"},
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "gone"
