"""A request number in network_log names the same request until it is no longer tracked, then fails loudly."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.browser_session_network_mixin import BrowserSessionNetworkMixin
from myrm_agent_harness.toolkits.browser.session.network_intelligence import NetworkIntelligence


def _see(ni: NetworkIntelligence, request_id: str, resource_type: str = "XHR") -> None:
    ni._on_request_will_be_sent(
        {
            "requestId": request_id,
            "type": resource_type,
            "request": {"url": f"https://api.example.com/{request_id}", "method": "GET"},
        }
    )


def _with_cdp(ni: NetworkIntelligence, body: str = "{}") -> AsyncMock:
    send = AsyncMock(return_value={"body": body, "base64Encoded": False})
    cdp = AsyncMock()
    cdp.send = send
    ni._cdp_session = cdp
    return send


def test_numbers_count_api_requests_only_so_documents_leave_no_gaps() -> None:
    ni = NetworkIntelligence()
    for request_id, resource_type in [("doc-1", "Document"), ("a", "XHR"), ("doc-2", "Document"), ("b", "Fetch")]:
        _see(ni, request_id, resource_type)

    assert [(r.seq, r.request_id) for r in ni.get_api_requests()] == [(1, "a"), (2, "b")]
    assert [line.split(". ")[0].strip() for line in ni.get_summary().splitlines()] == ["1", "2"]


def test_a_number_keeps_naming_its_request_after_older_ones_are_evicted() -> None:
    ni = NetworkIntelligence(max_requests=5)
    for i in range(1, 9):
        _see(ni, f"req-{i}")

    assert ni.find_api_request(1) is None
    assert ni.find_api_request(3) is None
    found = ni.find_api_request(4)
    assert found is not None and found.request_id == "req-4"
    assert ni.get_summary().splitlines()[0].strip().startswith("4. GET https://api.example.com/req-4")


def test_evicting_documents_does_not_renumber_api_requests() -> None:
    ni = NetworkIntelligence(max_requests=4)
    _see(ni, "a")
    for i in range(3):
        _see(ni, f"doc-{i}", "Document")
    _see(ni, "b")

    assert [(r.seq, r.request_id) for r in ni.get_api_requests()] == [(2, "b")]


def test_a_response_update_keeps_the_requests_number() -> None:
    ni = NetworkIntelligence()
    _see(ni, "a")
    _see(ni, "b")

    ni._on_response_received({"requestId": "b", "response": {"status": 200, "mimeType": "application/json"}})

    found = ni.find_api_request(2)
    assert found is not None and (found.request_id, found.status) == ("b", 200)


def test_clearing_never_reuses_a_number() -> None:
    ni = NetworkIntelligence()
    _see(ni, "a")
    ni.clear()
    _see(ni, "b")

    assert ni.find_api_request(1) is None
    found = ni.find_api_request(2)
    assert found is not None and found.request_id == "b"


@pytest.mark.parametrize("seq", [0, -1])
def test_numbers_below_one_name_no_request(seq: int) -> None:
    ni = NetworkIntelligence()
    _see(ni, "doc", "Document")
    _see(ni, "a")

    assert ni.find_api_request(seq) is None


def test_the_invalid_index_error_names_the_tracked_range_and_how_to_refresh() -> None:
    ni = NetworkIntelligence(max_requests=3)
    assert "No API requests are tracked" in ni.invalid_index_error(1)

    for i in range(1, 6):
        _see(ni, f"req-{i}")

    error = ni.invalid_index_error(1)
    assert error.startswith("Error: Invalid index 1.")
    assert "Valid range: 3-5" in error
    assert "network_log" in error


@pytest.mark.asyncio
async def test_a_response_body_is_never_taken_from_a_different_request_than_the_one_listed() -> None:
    # The window was full when the model read the log; two more requests came in before it asked for #1.
    ni = NetworkIntelligence(max_requests=3)
    for i in range(1, 4):
        _see(ni, f"req-{i}")
    send = _with_cdp(ni, "heartbeat body")
    _see(ni, "req-4")
    _see(ni, "req-5")

    result = await ni.get_response_body(1)

    assert result.startswith("Error: Invalid index 1.")
    assert "Valid range: 3-5" in result
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_response_body_is_fetched_by_the_number_the_log_showed() -> None:
    ni = NetworkIntelligence(max_requests=3)
    for i in range(1, 6):
        _see(ni, f"req-{i}")
    send = _with_cdp(ni, "the body")

    assert await ni.get_response_body(4) == "the body"
    send.assert_awaited_once_with("Network.getResponseBody", {"requestId": "req-4"})


class _Session(BrowserSessionNetworkMixin):
    def __init__(self, ni: NetworkIntelligence) -> None:
        self._network_intelligence = ni
        self.page = MagicMock()
        self.page.evaluate = AsyncMock(return_value=[200, "ok"])
        self._tab_controller = MagicMock()
        self._tab_controller.get_active_page.return_value = self.page

    async def _ensure_components(self) -> None:
        """The replay needs only the active page; no browser components are built."""


@pytest.mark.asyncio
async def test_a_replay_never_resends_a_different_request_than_the_one_listed() -> None:
    ni = NetworkIntelligence(max_requests=3)
    for i in range(1, 4):
        _see(ni, f"req-{i}")
    session = _Session(ni)
    _see(ni, "req-4")
    _see(ni, "req-5")

    result = await session.replay_network_request(1)

    assert result.startswith("Error: Invalid index 1.")
    session.page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_replay_resends_the_request_with_the_number_the_log_showed() -> None:
    ni = NetworkIntelligence(max_requests=3)
    for i in range(1, 6):
        _see(ni, f"req-{i}")
    session = _Session(ni)

    assert await session.replay_network_request(5) == "[HTTP 200]\nok"
    assert "https://api.example.com/req-5" in session.page.evaluate.call_args[0][0]
