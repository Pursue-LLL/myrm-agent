"""Tests for url_dedup_key on site-root spellings and on display URLs.

A URL with a host and no path names the root page. An empty path and ``/`` are one resource (RFC 3986 section 6.2.3);
a run of slashes is folded into the root as this project's own comparison rule. They share one key, and anything that
tells pages apart does not. A display URL keeps the key of the URL it was made from.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.utils.url_utils import readable_url, url_dedup_key


@pytest.mark.parametrize(
    ("spelling", "key"),
    [
        ("https://example.com", "https://example.com/"),
        ("https://example.com/", "https://example.com/"),
        ("https://example.com//", "https://example.com/"),
        ("https://example.com///", "https://example.com/"),
        ("https://Example.COM", "https://example.com/"),
        ("https://www.example.com", "https://example.com/"),
        ("https://example.com:8080", "https://example.com:8080/"),
        ("https://example.com?q=1", "https://example.com/?q=1"),
    ],
)
def test_root_spellings_share_one_key(spelling: str, key: str) -> None:
    assert url_dedup_key(spelling) == key


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("https://example.com", "https://example.org"),
        ("https://example.com", "https://example.com/a"),
        ("https://example.com", "http://example.com"),
        ("https://example.com?q=1", "https://example.com/?q=2"),
    ],
)
def test_pages_that_differ_keep_different_keys(first: str, second: str) -> None:
    assert url_dedup_key(first) != url_dedup_key(second)


def test_kept_fragments_tell_root_anchors_apart() -> None:
    anchor_a = url_dedup_key("https://example.com#a", keep_fragment=True)
    assert anchor_a == url_dedup_key("https://example.com/#a", keep_fragment=True)
    assert anchor_a != url_dedup_key("https://example.com/#b", keep_fragment=True)


@pytest.mark.parametrize("keep_fragment", [False, True])
@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/%E6%90%9C%E7%B4%A2",
        "https://example.com/?q=%E6%90%9C%E7%B4%A2",
        "https://example.com/%E6%90%9C#%E4%BD%A0",
    ],
)
def test_the_display_url_has_the_key_of_the_original(url: str, keep_fragment: bool) -> None:
    shown = readable_url(url)
    assert shown != url, "a display URL equal to its original would make this test check nothing"
    assert url_dedup_key(shown, keep_fragment=keep_fragment) == url_dedup_key(url, keep_fragment=keep_fragment)
