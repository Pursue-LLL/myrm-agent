"""network_log is one list: the numbered XHR/Fetch requests, then the other resources that failed, unnumbered.

A number in the list is a number network_detail / network_replay accept, so a failed script or document carries
none: it could otherwise be mistaken for the API request that holds that number. The failed resources are listed
even when the page made no XHR/Fetch request (a white page whose script 404s), and a URL the list cut is given
in full by network_detail.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.browser.session.browser_session_network_mixin import (
    _API_LIST_HEADER,
    _DETAIL_URL_MAX,
    BrowserSessionNetworkMixin,
)
from myrm_agent_harness.toolkits.browser.session.network.intelligence import NetworkIntelligence
from myrm_agent_harness.toolkits.browser.session.network.logger import (
    URL_PREVIEW_CHARS,
    NetworkLogger,
    RequestInfo,
)

_FAILED_HEADER = "Other failed requests (not numbered, so network_detail cannot open them):"


class _Session(BrowserSessionNetworkMixin):
    """Minimal mixin stand-in over a real NetworkIntelligence and a real NetworkLogger."""

    def __init__(self) -> None:
        self._network_intelligence = NetworkIntelligence()
        self._network_logger = NetworkLogger()

    def xhr(self, url: str, request_id: str = "req-1") -> None:
        self._network_intelligence._on_request_will_be_sent(
            {"requestId": request_id, "type": "XHR", "request": {"url": url, "method": "GET"}}
        )

    def driver_saw(self, url: str, resource_type: str, status: int) -> None:
        self._network_logger._requests.append(RequestInfo("GET", url, resource_type, 0.0, status=status))

    def body_is(self, body: str) -> None:
        cdp = AsyncMock()
        cdp.send = AsyncMock(return_value={"body": body, "base64Encoded": False})
        self._network_intelligence._cdp_session = cdp


def test_a_failed_script_is_listed_apart_from_the_numbered_api_requests() -> None:
    session = _Session()
    session.xhr("https://app.example.com/api/ok")
    session.driver_saw("https://app.example.com/static/main.js", "script", 404)

    assert session.get_network_log().splitlines() == [
        _API_LIST_HEADER,
        "  1. GET https://app.example.com/api/ok [pending]",
        "",
        _FAILED_HEADER,
        "  script GET https://app.example.com/static/main.js [404]",
    ]


@pytest.mark.asyncio
async def test_the_number_one_opens_the_api_request_never_the_failed_script() -> None:
    session = _Session()
    session.xhr("https://app.example.com/api/ok")
    session.driver_saw("https://app.example.com/static/main.js", "script", 404)
    session.body_is('{"ok":1}')

    assert await session.get_network_detail(1) == '{"ok":1}'


def test_failed_resources_are_listed_when_the_page_made_no_api_request() -> None:
    session = _Session()
    session.driver_saw("https://app.example.com/static/main.js", "script", 404)

    assert session.get_network_log().splitlines() == [
        "No API requests captured.",
        "",
        _FAILED_HEADER,
        "  script GET https://app.example.com/static/main.js [404]",
    ]


def test_an_empty_log_says_no_api_request_was_captured() -> None:
    assert _Session().get_network_log() == "No API requests captured."


def test_a_resource_that_loaded_is_not_listed() -> None:
    session = _Session()
    session.driver_saw("https://app.example.com/static/main.js", "script", 200)

    assert session.get_network_log() == "No API requests captured."


def test_without_cdp_the_drivers_own_api_list_stands_in_and_the_failed_resources_follow() -> None:
    session = _Session()
    session.driver_saw("https://app.example.com/api/ok", "xhr", 200)
    session.driver_saw("https://app.example.com/static/main.js", "script", 404)

    lines = session.get_network_log().splitlines()

    assert lines[0] == "Network Log (1 total, showing last 1):"
    assert "1. GET https://app.example.com/api/ok" in lines
    assert lines[-2:] == [_FAILED_HEADER, "  script GET https://app.example.com/static/main.js [404]"]


class TestDetailGivesBackTheUrlTheListCut:
    @pytest.mark.asyncio
    async def test_a_cut_url_comes_in_full_ahead_of_the_body(self) -> None:
        url = "https://api.example.com/search?q=" + "a" * 300
        session = _Session()
        session.xhr(url)
        session.body_is('{"hits":[]}')

        assert url[: URL_PREVIEW_CHARS - 1] + "…" in session.get_network_log()
        assert await session.get_network_detail(1) == f'URL: {url}\n{{"hits":[]}}'

    @pytest.mark.asyncio
    async def test_a_url_the_list_showed_whole_is_not_repeated(self) -> None:
        session = _Session()
        session.xhr("https://api.example.com/search?q=a")
        session.body_is('{"hits":[]}')

        assert await session.get_network_detail(1) == '{"hits":[]}'

    @pytest.mark.asyncio
    async def test_the_full_url_is_masked_like_the_listed_one(self) -> None:
        secret = "abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        url = "https://api.example.com/data?p=" + "x" * 200 + "&access_token=" + secret + "&z=1"
        session = _Session()
        session.xhr(url)
        session.body_is("{}")

        answer = await session.get_network_detail(1)

        assert secret[:12] not in answer
        assert answer.splitlines()[0].endswith("&access_token=***&z=1")

    @pytest.mark.asyncio
    async def test_a_url_beyond_the_detail_limit_is_cut_there_and_says_so(self) -> None:
        session = _Session()
        session.xhr("https://api.example.com/" + "a" * (_DETAIL_URL_MAX + 500))
        session.body_is("{}")

        first_line = (await session.get_network_detail(1)).splitlines()[0]

        assert len(first_line) == len("URL: ") + _DETAIL_URL_MAX
        assert first_line.endswith("…")

    @pytest.mark.asyncio
    async def test_a_number_that_names_no_request_gets_the_error_alone(self) -> None:
        session = _Session()
        session.xhr("https://api.example.com/search?q=" + "a" * 300)
        session.body_is("{}")

        answer = await session.get_network_detail(9)

        assert answer.startswith("Error: Invalid index 9.")
        assert "URL:" not in answer
