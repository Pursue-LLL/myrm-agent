"""The CDP recorder lists the page the model is looking at, and only data: no earlier page's requests, no files.

A number network_log shows is a number network_detail / network_replay take, so a request of a page that is gone must
not stay listed: the model would read it as this page's. The page changes when the main frame commits a new document
(`Page.frameNavigated` without a `parentId`) or when the recorder attaches to another page; a sub-frame or a
`pushState` route change is the same page. A response whose MIME type is an image, audio, video or font is a file
that fills the window and cannot be read as text, so it only counts.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.network.intelligence import NetworkIntelligence

_API = "https://api.example.com"


def _sent(ni: NetworkIntelligence, request_id: str, path: str = "/data") -> None:
    ni._on_request_will_be_sent(
        {"requestId": request_id, "type": "XHR", "request": {"url": f"{_API}{path}", "method": "GET"}}
    )


def _answered(ni: NetworkIntelligence, request_id: str, mime: str = "application/json", status: int = 200) -> None:
    ni._on_response_received({"requestId": request_id, "response": {"status": status, "mimeType": mime}})


def _main_frame_navigated(ni: NetworkIntelligence) -> None:
    ni._on_frame_navigated({"frame": {}})


def _sub_frame_navigated(ni: NetworkIntelligence) -> None:
    ni._on_frame_navigated({"frame": {"parentId": "main-frame"}})


def _with_cdp(ni: NetworkIntelligence, error: Exception | None = None) -> AsyncMock:
    send = AsyncMock(side_effect=error) if error else AsyncMock(return_value={"body": "{}", "base64Encoded": False})
    ni._cdp_session = MagicMock(send=send)
    return send


def _cdp_page() -> MagicMock:
    page = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=AsyncMock(on=MagicMock()))
    return page


def _seqs(ni: NetworkIntelligence) -> list[int]:
    return [record.seq for record in ni.get_api_requests()]


class TestAnEarlierPageIsNotListed:
    def test_a_new_document_in_the_main_frame_starts_the_list_over(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "a")
        _sent(ni, "b")

        _main_frame_navigated(ni)
        _sent(ni, "c")

        assert _seqs(ni) == [3]
        assert [line.split(". ")[0].strip() for line in ni.get_summary().splitlines()] == ["3"]

    def test_a_sub_frame_navigation_is_the_same_page(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "a")

        _sub_frame_navigated(ni)
        _sent(ni, "b")

        assert _seqs(ni) == [1, 2]

    def test_numbers_are_not_reused_by_the_next_page(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "a")

        _main_frame_navigated(ni)
        _sent(ni, "b")

        assert ni.find_api_request(1) is None
        assert ni.find_api_request(2) is not None

    @pytest.mark.asyncio
    async def test_an_earlier_pages_number_is_refused_and_no_body_is_asked_for(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "a")
        _main_frame_navigated(ni)
        _sent(ni, "b")
        send = _with_cdp(ni)

        answer = await ni.get_response_body(1)

        assert answer.startswith("Error: Invalid index 1. Valid range: 2;")
        assert "network_log" in answer
        send.assert_not_awaited()

    def test_a_page_with_no_request_yet_says_so_instead_of_naming_a_range(self) -> None:
        ni = NetworkIntelligence()
        _with_cdp(ni)
        _sent(ni, "a")

        _main_frame_navigated(ni)

        assert ni.get_summary() == ""
        assert ni.invalid_index_error(1) == (
            "Error: Invalid index 1. No API requests are tracked on the current page; run network_log to refresh."
        )

    def test_the_records_of_earlier_pages_are_dropped_by_the_window_like_any_other(self) -> None:
        ni = NetworkIntelligence(max_requests=2)
        _sent(ni, "a")
        _main_frame_navigated(ni)
        assert ni.hidden_summary() == "(not listed: requests of earlier pages)"

        _sent(ni, "b")
        _sent(ni, "c")

        assert _seqs(ni) == [2, 3]
        assert ni.hidden_summary() == ""

    def test_a_late_answer_for_an_earlier_pages_request_does_not_touch_this_pages_list(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "old")
        _main_frame_navigated(ni)
        _sent(ni, "new")

        _answered(ni, "old", status=500)

        assert [(r.seq, r.status) for r in ni.get_api_requests()] == [(2, None)]


class TestAttachingToAnotherPage:
    @pytest.mark.asyncio
    async def test_the_list_of_the_page_that_was_shown_before_is_not_listed(self) -> None:
        ni = NetworkIntelligence()
        await ni.attach(_cdp_page())
        _sent(ni, "a")

        await ni.attach(_cdp_page())

        assert ni.get_api_requests() == []
        assert ni.hidden_summary() == "(not listed: requests of earlier pages)"

    @pytest.mark.asyncio
    async def test_attaching_to_the_page_already_attached_changes_nothing(self) -> None:
        ni = NetworkIntelligence()
        page = _cdp_page()
        await ni.attach(page)
        _sent(ni, "a")

        await ni.attach(page)

        assert _seqs(ni) == [1]

    @pytest.mark.asyncio
    async def test_a_page_the_recorder_cannot_attach_to_still_does_not_show_the_previous_pages_list(self) -> None:
        ni = NetworkIntelligence()
        await ni.attach(_cdp_page())
        _sent(ni, "a")
        broken = MagicMock()
        broken.context.new_cdp_session = AsyncMock(side_effect=RuntimeError("target closed"))

        await ni.attach(broken)

        assert not ni.is_enabled
        assert ni.get_api_requests() == []


class TestFilesAreCountedNotListed:
    @pytest.mark.parametrize("mime", ["image/png", "image/svg+xml", "audio/mpeg", "video/mp4", "font/woff2"])
    def test_a_file_response_leaves_the_list(self, mime: str) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "data")
        _sent(ni, "file")
        _answered(ni, "data")

        _answered(ni, "file", mime=mime)

        assert _seqs(ni) == [1]
        assert ni.hidden_summary() == "(not listed: 1 image, audio, video and font responses)"

    @pytest.mark.parametrize(
        "mime", ["application/json", "text/html", "application/octet-stream", "application/pdf", "application/wasm"]
    )
    def test_any_other_response_stays_listed(self, mime: str) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "a")

        _answered(ni, "a", mime=mime)

        assert _seqs(ni) == [1]
        assert ni.hidden_summary() == ""

    def test_the_numbers_of_the_requests_left_keep_their_gaps_and_the_error_names_them(self) -> None:
        ni = NetworkIntelligence()
        _with_cdp(ni)
        for request_id in ("a", "b", "c", "d"):
            _sent(ni, request_id)
        _answered(ni, "b", mime="image/png")

        assert _seqs(ni) == [1, 3, 4]
        assert "Valid range: 1, 3-4;" in ni.invalid_index_error(2)

    def test_a_file_that_answered_after_the_page_changed_is_not_counted_for_the_new_page(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "old")
        _main_frame_navigated(ni)

        _answered(ni, "old", mime="image/png")

        assert ni.hidden_summary() == ""

    def test_the_count_starts_over_with_the_next_page(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "file")
        _answered(ni, "file", mime="image/png")
        assert ni.hidden_summary() != ""

        _main_frame_navigated(ni)

        assert ni.hidden_summary() == ""

    def test_the_line_names_both_what_is_counted_and_what_was_left_with_the_earlier_page(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "old")
        _main_frame_navigated(ni)
        _sent(ni, "file")

        _answered(ni, "file", mime="font/woff2")

        assert ni.hidden_summary() == (
            "(not listed: requests of earlier pages; 1 image, audio, video and font responses)"
        )

    def test_a_failure_that_follows_a_file_response_changes_nothing(self) -> None:
        ni = NetworkIntelligence()
        _sent(ni, "file")
        _answered(ni, "file", mime="image/png")

        ni._on_loading_failed({"requestId": "file", "errorText": "net::ERR_ABORTED"})

        assert ni.get_api_requests() == []
        assert ni.hidden_summary() == "(not listed: 1 image, audio, video and font responses)"


class TestTruthfulErrors:
    @pytest.mark.asyncio
    async def test_a_session_without_cdp_says_there_is_no_cdp_not_that_the_number_is_invalid(self) -> None:
        ni = NetworkIntelligence()

        for answer in (ni.invalid_index_error(1), await ni.get_response_body(1)):
            assert answer.startswith("Error: No CDP connection")
            assert "Invalid index" not in answer

    @pytest.mark.asyncio
    async def test_the_expired_body_error_echoes_a_bounded_masked_url(self) -> None:
        secret = "abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        ni = NetworkIntelligence()
        ni._on_request_will_be_sent(
            {
                "requestId": "a",
                "type": "XHR",
                "request": {"url": f"{_API}/data?access_token={secret}&pad=" + "x" * 5000, "method": "GET"},
            }
        )
        _with_cdp(ni, error=RuntimeError("No resource with given identifier found"))

        answer = await ni.get_response_body(1)

        assert answer.startswith("Error: Response body no longer available for request #1 (GET https://api.example.com")
        assert secret[:12] not in answer
        assert len(answer) < 500
