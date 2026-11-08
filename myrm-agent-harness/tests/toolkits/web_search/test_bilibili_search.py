"""Unit tests for Bilibili search fast-path.

Tests cover:
- is_bilibili_video_query: which queries their site: operators scope to Bilibili videos
- search_bilibili: the requested keyword never carries site: operators; edge cases (mocked HTTP)

[POS]
Unit tests for bilibili_search.py. Engine routing is covered in test_fast_search_merge.py.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.web_search.providers.bilibili_search import (
    _format_play_count,
    _strip_html,
    is_bilibili_video_query,
    search_bilibili,
)


class TestIsBilibiliVideoQuery:
    """Detection precision: only site: operators that scope a query to Bilibili videos count, not mentions of it."""

    @pytest.mark.parametrize(
        "query",
        [
            "site:bilibili.com LLM",
            'site:bilibili.com "Docker 教程"',
            "site:bilibili.com/video LLM",
            "site:bilibili.com/video/BV1hp4y1k7SV LLM",
            "LLM site:bilibili.com/Video",
            'site:"bilibili.com" LLM',
            "LLM (site:Bilibili.com)",
            "site:bilibili.com -site:reddit.com redis",
        ],
    )
    def test_positive_detection(self, query: str) -> None:
        assert is_bilibili_video_query(query)

    @pytest.mark.parametrize(
        "query",
        [
            # Mentioning Bilibili is no scope, whatever the phrasing: the model scopes a query with site:.
            "bilibili stock price",
            "bilibili company revenue 2026",
            "搜B站上关于LLM的视频",
            "B站上有没有Rust入门教程",
            "查哔哩哔哩 2026 Q3 财报",
            "Python latest news",
            "how to use docker",
            # A site: operator scopes to Bilibili videos only when every domain it includes is bilibili.com or
            # its video section.
            "python tutorial -site:bilibili.com",
            "site:bilibili.com.cn video",
            "site:bilibili.com site:github.com redis",
            "site:bilibili.com/video site:bilibili.com/read redis",
            "site:www.bilibili.com video",
            # The video API cannot return the documents of the other sections.
            "site:bilibili.com/read redis",
            "site:bilibili.com/videos redis",
        ],
    )
    def test_negative_detection(self, query: str) -> None:
        assert not is_bilibili_video_query(query)


class TestStripHtml:
    """HTML tag removal utility."""

    def test_removes_em_tags(self) -> None:
        assert _strip_html('<em class="keyword">Python</em>教程') == "Python教程"

    def test_removes_nested_tags(self) -> None:
        assert _strip_html("<b><em>hello</em></b>") == "hello"

    def test_no_tags(self) -> None:
        assert _strip_html("plain text") == "plain text"

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""


class TestFormatPlayCount:
    """Play count formatting (万 unit)."""

    def test_below_threshold(self) -> None:
        assert _format_play_count(9999) == "9999"

    def test_exactly_10000(self) -> None:
        assert _format_play_count(10000) == "1.0万"

    def test_large_number(self) -> None:
        assert _format_play_count(1681000) == "168.1万"

    def test_zero(self) -> None:
        assert _format_play_count(0) == "0"


_ONE_VIDEO_PAYLOAD = {
    "code": 0,
    "data": {
        "result": [
            {
                "result_type": "video",
                "data": [
                    {
                        "title": "Docker 教程",
                        "author": "UP",
                        "play": 1000,
                        "duration": "10:00",
                        "bvid": "BV1xx411c7xx",
                        "description": "desc",
                    }
                ],
            }
        ]
    },
}


@contextmanager
def _mock_api(payload: Mapping[str, object]) -> Iterator[MagicMock]:
    """Serve ``payload`` as the API response and yield the ``urlopen`` mock, whose call holds the requested URL."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        yield mock_urlopen


def _requested_keyword(mock_urlopen: MagicMock) -> str:
    request: urllib.request.Request = mock_urlopen.call_args.args[0]
    return urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)["keyword"][0]


def _video_payload(entries: list[dict[str, object]]) -> dict[str, object]:
    """The API answer whose video group holds ``entries``."""
    return {"code": 0, "data": {"result": [{"result_type": "video", "data": entries}]}}


class TestSearchBilibili:
    """search_bilibili function with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_empty_keyword_returns_none(self) -> None:
        assert await search_bilibili("") is None
        assert await search_bilibili("  ") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("keyword", "requested"),
        [
            ('site:bilibili.com "Docker 教程"', '"Docker 教程"'),
            ("Rust 入门 site:bilibili.com/video", "Rust 入门"),
            ("Rust 入门 教程", "Rust 入门 教程"),
        ],
    )
    async def test_site_operators_never_reach_the_api(self, keyword: str, requested: str) -> None:
        with _mock_api(_ONE_VIDEO_PAYLOAD) as mock_urlopen:
            assert await search_bilibili(keyword) is not None

            assert _requested_keyword(mock_urlopen) == requested

    @pytest.mark.asyncio
    async def test_a_keyword_that_is_only_operators_makes_no_request(self) -> None:
        with patch("urllib.request.urlopen") as mock_urlopen:
            assert await search_bilibili("site:bilibili.com -site:reddit.com") is None

            mock_urlopen.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_results_clamped(self) -> None:
        mock_response = {
            "code": 0,
            "data": {
                "result": [
                    {
                        "result_type": "video",
                        "data": [
                            {
                                "title": f"Video {i}",
                                "author": "UP",
                                "play": 1000,
                                "duration": "10:00",
                                "bvid": f"BV{i:010d}",
                                "description": "desc",
                            }
                            for i in range(5)
                        ],
                    }
                ]
            },
        }
        with _mock_api(mock_response):
            result = await search_bilibili("test", max_results=0)
            assert result is not None
            assert len(result) == 1  # clamped to min 1

    @pytest.mark.asyncio
    async def test_api_returns_null_data(self) -> None:
        """Regression: API returns {"code": 0, "data": null}."""
        mock_response = {"code": 0, "data": None}
        with _mock_api(mock_response):
            result = await search_bilibili("test", max_results=5)
            assert result is None  # graceful fallback

    @pytest.mark.asyncio
    async def test_api_returns_nonzero_code(self) -> None:
        mock_response = {"code": -412, "data": None}
        with _mock_api(mock_response):
            result = await search_bilibili("test", max_results=5)
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_search(self) -> None:
        mock_response = {
            "code": 0,
            "data": {
                "result": [
                    {
                        "result_type": "video",
                        "data": [
                            {
                                "title": '<em class="keyword">Rust</em>教程',
                                "author": "软件工艺师",
                                "play": 1681000,
                                "duration": "729:37",
                                "bvid": "BV1hp4y1k7SV",
                                "description": "配套教材",
                            }
                        ],
                    }
                ]
            },
        }
        with _mock_api(mock_response):
            results = await search_bilibili("Rust教程", max_results=5)
            assert results is not None
            assert len(results) == 1
            r = results[0]
            assert r.title == "Rust教程"  # HTML cleaned
            assert r.link == "https://www.bilibili.com/video/BV1hp4y1k7SV"
            assert "168.1万" in r.snippet
            assert "软件工艺师" in r.snippet

    @pytest.mark.asyncio
    async def test_live_rooms_without_a_bvid_take_no_result_slot(self) -> None:
        """The video group also lists live rooms: they have no bvid, so no video to link to."""
        live_room: dict[str, object] = {"type": "live_room", "title": "Live", "bvid": "", "arcurl": ""}
        videos: list[dict[str, object]] = [
            {"type": "video", "title": f"Video {i}", "bvid": f"BV1xx411c7x{i}"} for i in range(2)
        ]
        with _mock_api(_video_payload([live_room, *videos])):
            results = await search_bilibili("test", max_results=2)

        assert results is not None
        assert [r.link for r in results] == [f"https://www.bilibili.com/video/BV1xx411c7x{i}" for i in range(2)]

    @pytest.mark.asyncio
    async def test_a_video_group_with_only_live_rooms_returns_none(self) -> None:
        live_room: dict[str, object] = {"type": "live_room", "title": "Live", "bvid": ""}
        with _mock_api(_video_payload([live_room])):
            assert await search_bilibili("test") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("raw_title", "title"),
        [
            ("Tom &amp; Jerry &#x27;s", "Tom & Jerry 's"),
            ('<em class="keyword">Q</em>&amp;A', "Q&A"),
            ("&lt;em&gt;literal&lt;/em&gt;", "<em>literal</em>"),
        ],
    )
    async def test_html_entities_are_decoded_after_tags_are_stripped(self, raw_title: str, title: str) -> None:
        entry: dict[str, object] = {"title": raw_title, "bvid": "BV1xx411c7xx", "description": "Q&amp;A &lt;3"}
        with _mock_api(_video_payload([entry])):
            results = await search_bilibili("test")

        assert results is not None
        assert results[0].title == title
        assert results[0].snippet == "Q&A <3"

    @pytest.mark.asyncio
    async def test_a_null_description_keeps_the_video(self) -> None:
        """The API may send null for the description: the video stays a result, its snippet falls back to the title."""
        entry: dict[str, object] = {"title": "Docker 教程", "bvid": "BV1xx411c7xx", "description": None}
        with _mock_api(_video_payload([entry])):
            results = await search_bilibili("test")

        assert results is not None
        assert [(r.title, r.snippet) for r in results] == [("Docker 教程", "Docker 教程")]

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = await search_bilibili("test", max_results=3)
            assert result is None
