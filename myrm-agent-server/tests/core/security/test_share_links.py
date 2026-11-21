"""Tests for the share link builder (share_links)."""

import pytest

from app.core.security.share.share_links import ShareKind, share_link_path, share_link_url


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        (ShareKind.ARTIFACT, "/api/v1/public/artifact-share/tok-1"),
        (ShareKind.CHAT, "/api/v1/public/chat-share/tok-1"),
    ],
)
def test_path_and_url_per_kind(kind: ShareKind, path: str) -> None:
    assert share_link_path(kind, "tok-1") == path
    assert share_link_url(kind, "tok-1", "https://host.example.com") == f"https://host.example.com{path}"


def test_every_share_kind_is_served_under_the_public_api_prefix() -> None:
    for kind in ShareKind:
        assert share_link_path(kind, "t").startswith("/api/v1/public/")
