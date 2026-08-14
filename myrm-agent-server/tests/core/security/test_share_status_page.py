"""Unit tests for the shared share status page module."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.security.share_status_page import (
    render_share_status_html,
    share_not_found,
    wants_html,
)


def _request(accept: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if accept is not None:
        headers.append((b"accept", accept.encode()))
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
    html = render_share_status_html(title="Link Revoked", message="This share link has been revoked by its owner.")
    assert "<title>Link Revoked</title>" in html
    assert "This share link has been revoked by its owner." in html
    assert 'name="robots" content="noindex, nofollow"' in html
    assert "Shared via Myrm Agent" in html


def test_share_not_found_answers_browser_with_html_404() -> None:
    response = share_not_found(
        _request("text/html"),
        detail="gone",
        title="Link Expired",
        message="This share link has expired.",
        headers={"X-Robots-Tag": "noindex, nofollow"},
    )
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert "This share link has expired." in response.body.decode()


def test_share_not_found_raises_json_404_for_api_clients() -> None:
    for accept in ("application/json", None):
        with pytest.raises(HTTPException) as exc_info:
            share_not_found(
                _request(accept),
                detail="gone",
                title="Link Expired",
                message="This share link has expired.",
                headers={"X-Robots-Tag": "noindex, nofollow"},
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "gone"
