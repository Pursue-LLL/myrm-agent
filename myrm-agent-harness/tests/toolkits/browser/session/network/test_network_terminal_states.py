"""A request that has ended must not read as `[pending]`.

A redirect hop names its status and the request that carries on from it; a failed request names its
error. Only a request that is really still in flight is `[pending]`: the model waits on that word, so
using it for a request that will never answer sends it into a wait that cannot end.

A response that arrived and was then dropped by the page itself (an empty body nobody read, an aborted
stream) is not a failure: Chrome reports it as canceled, but the server's answer stands.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.network.intelligence import (
    NetworkIntelligence,
    _CdpLoadingFailed,
    _CdpRequestWillBeSent,
)

_API = "https://api.example.com"


def _sent(
    ni: NetworkIntelligence,
    request_id: str,
    path: str = "/data",
    *,
    redirected_from: int | None = None,
) -> None:
    """The browser starts a request; `redirected_from` is the status of the hop that sent it here."""
    params: _CdpRequestWillBeSent = {
        "requestId": request_id,
        "type": "XHR",
        "request": {"url": f"{_API}{path}", "method": "GET"},
    }
    if redirected_from is not None:
        params["redirectResponse"] = {"status": redirected_from, "mimeType": ""}
    ni._on_request_will_be_sent(params)


def _answered(ni: NetworkIntelligence, request_id: str, status: int = 200) -> None:
    ni._on_response_received({"requestId": request_id, "response": {"status": status, "mimeType": "application/json"}})


def _failed(
    ni: NetworkIntelligence, request_id: str, error: str, cors: str | None = None, *, canceled: bool = False
) -> None:
    params: _CdpLoadingFailed = {"requestId": request_id, "errorText": error, "canceled": canceled}
    if cors is not None:
        params["corsErrorStatus"] = {"corsError": cors}
    ni._on_loading_failed(params)


def _lines(ni: NetworkIntelligence) -> list[str]:
    return [line.strip() for line in ni.get_summary().splitlines()]


def _with_cdp(ni: NetworkIntelligence, body: str = "{}") -> AsyncMock:
    send = AsyncMock(return_value={"body": body, "base64Encoded": False})
    cdp = AsyncMock()
    cdp.send = send
    ni._cdp_session = cdp
    return send


def test_a_request_still_in_flight_stays_pending() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")

    assert _lines(ni) == [f"1. GET {_API}/data [pending]"]


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_hop_takes_its_status_when_the_next_hop_starts(status: int) -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "r", "/target", redirected_from=status)
    _answered(ni, "r")

    assert _lines(ni) == [f"1. GET {_API}/hop [{status}]", f"2. GET {_API}/target [200]"]


def test_a_redirect_fills_in_only_the_hop_it_continues() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "other", "/unrelated")
    _sent(ni, "r", "/target", redirected_from=302)

    assert _lines(ni) == [
        f"1. GET {_API}/hop [302]",
        f"2. GET {_API}/unrelated [pending]",
        f"3. GET {_API}/target [pending]",
    ]


def test_a_redirect_whose_first_hop_left_the_window_changes_no_other_request() -> None:
    ni = NetworkIntelligence(max_requests=2)
    _sent(ni, "r", "/hop")
    _sent(ni, "x", "/x")
    _sent(ni, "y", "/y")
    _sent(ni, "r", "/target", redirected_from=302)

    assert _lines(ni) == [f"3. GET {_API}/y [pending]", f"4. GET {_API}/target [pending]"]


@pytest.mark.asyncio
async def test_the_body_of_a_redirect_hop_is_the_next_request_not_a_fetch_from_chrome() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "r", "/target", redirected_from=302)
    _answered(ni, "r")
    send = _with_cdp(ni, "the final body")

    assert await ni.get_response_body(1) == "Redirected (302); the response is request #2"
    send.assert_not_awaited()
    assert await ni.get_response_body(2) == "the final body"
    send.assert_awaited_once_with("Network.getResponseBody", {"requestId": "r"})


@pytest.mark.asyncio
async def test_a_hop_whose_status_is_unknown_still_points_at_the_request_that_carries_on() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "r", "/target")
    _with_cdp(ni)

    assert await ni.get_response_body(1) == "Redirected; the response is request #2"


def test_a_failed_request_shows_its_error_instead_of_pending() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _failed(ni, "a", "net::ERR_BLOCKED_BY_CLIENT.Inspector")

    assert _lines(ni) == [f"1. GET {_API}/data [failed: net::ERR_BLOCKED_BY_CLIENT.Inspector]"]


def test_a_cors_failure_names_the_cors_error() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _failed(ni, "a", "net::ERR_FAILED", cors="MissingAllowOriginHeader")

    assert _lines(ni) == [f"1. GET {_API}/data [failed: net::ERR_FAILED (CORS: MissingAllowOriginHeader)]"]


def test_a_failure_after_the_response_headers_still_reads_as_failed() -> None:
    """Chrome sends the response first and then fails the load (CORS, a body cut off mid-transfer)."""
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _answered(ni, "a")
    _failed(ni, "a", "net::ERR_FAILED", cors="MissingAllowOriginHeader")

    assert _lines(ni) == [f"1. GET {_API}/data [failed: net::ERR_FAILED (CORS: MissingAllowOriginHeader)]"]


def test_a_body_cut_off_after_the_response_headers_reads_as_failed() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _answered(ni, "a")
    _failed(ni, "a", "net::ERR_CONTENT_LENGTH_MISMATCH")

    assert _lines(ni) == [f"1. GET {_API}/data [failed: net::ERR_CONTENT_LENGTH_MISMATCH]"]


@pytest.mark.parametrize("status", [200, 204, 401, 500])
def test_a_response_the_page_dropped_keeps_the_status_the_server_gave(status: int) -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _answered(ni, "a", status)
    _failed(ni, "a", "net::ERR_ABORTED", canceled=True)

    assert _lines(ni) == [f"1. GET {_API}/data [{status}]"]


def test_a_request_cancelled_before_any_answer_reads_as_failed() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _failed(ni, "a", "net::ERR_ABORTED", canceled=True)

    assert _lines(ni) == [f"1. GET {_API}/data [failed: net::ERR_ABORTED]"]


def test_a_dropped_response_leaves_the_hops_before_it_alone() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "r", "/target", redirected_from=302)
    _answered(ni, "r")
    _failed(ni, "r", "net::ERR_ABORTED", canceled=True)

    assert _lines(ni) == [f"1. GET {_API}/hop [302]", f"2. GET {_API}/target [200]"]


def test_a_hop_cancelled_before_its_own_answer_fails_although_the_hop_before_it_was_answered() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "r", "/target", redirected_from=302)
    _failed(ni, "r", "net::ERR_ABORTED", canceled=True)

    assert _lines(ni) == [f"1. GET {_API}/hop [302]", f"2. GET {_API}/target [failed: net::ERR_ABORTED]"]


def test_the_final_status_of_a_redirected_request_is_that_of_its_last_hop() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "r", "/target", redirected_from=302)
    _answered(ni, "r", 403)

    first, last = ni.get_api_requests()

    assert (first.status, ni.final_status(first), ni.final_status(last)) == (302, 403, 403)


def test_the_final_status_of_a_request_nobody_answered_is_unknown() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")

    assert ni.final_status(ni.get_api_requests()[0]) is None


def test_a_failure_lands_on_the_last_hop_only() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "r", "/hop")
    _sent(ni, "r", "/target", redirected_from=302)
    _failed(ni, "r", "net::ERR_FAILED")

    assert _lines(ni) == [f"1. GET {_API}/hop [302]", f"2. GET {_API}/target [failed: net::ERR_FAILED]"]


def test_a_failure_for_a_request_that_is_not_tracked_is_ignored() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _failed(ni, "unknown", "net::ERR_FAILED")

    assert _lines(ni) == [f"1. GET {_API}/data [pending]"]


@pytest.mark.asyncio
async def test_the_body_of_a_failed_request_is_its_error_not_a_fetch_from_chrome() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _failed(ni, "a", "net::ERR_BLOCKED_BY_CLIENT.Inspector")
    send = _with_cdp(ni)

    assert await ni.get_response_body(1) == "Request failed: net::ERR_BLOCKED_BY_CLIENT.Inspector"
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_body_of_a_request_still_in_flight_is_still_asked_from_chrome() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    send = _with_cdp(ni, "partial")

    assert await ni.get_response_body(1) == "partial"
    send.assert_awaited_once_with("Network.getResponseBody", {"requestId": "a"})


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [204, 205, 304])
async def test_a_status_that_never_carries_a_body_says_so_without_asking_chrome(status: int) -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _answered(ni, "a", status)
    send = _with_cdp(ni)

    assert await ni.get_response_body(1) == f"No response body (status {status})"
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_empty_body_is_named_instead_of_returned_as_nothing() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _answered(ni, "a")
    _with_cdp(ni, "")

    assert await ni.get_response_body(1) == "Empty response"


@pytest.mark.asyncio
async def test_a_body_chrome_never_kept_is_explained_instead_of_quoting_the_driver() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _answered(ni, "a")
    _failed(ni, "a", "net::ERR_ABORTED", canceled=True)
    send = _with_cdp(ni)
    send.side_effect = RuntimeError(
        "CDPSession.send: Protocol error (Network.getResponseBody): No data found for resource with given identifier"
    )

    assert _lines(ni) == [f"1. GET {_API}/data [200]"]
    assert await ni.get_response_body(1) == (
        "The browser kept no body for this request: it may still be loading, or the page dropped it"
    )


@pytest.mark.asyncio
async def test_any_other_driver_error_is_still_reported_as_it_came() -> None:
    ni = NetworkIntelligence()
    _sent(ni, "a")
    _answered(ni, "a")
    _with_cdp(ni).side_effect = RuntimeError("Target closed")

    assert await ni.get_response_body(1) == "Error retrieving response body: Target closed"


@pytest.mark.asyncio
async def test_attach_listens_for_every_event_the_status_depends_on() -> None:
    page = MagicMock()
    cdp = AsyncMock()
    cdp.on = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=cdp)

    await NetworkIntelligence().attach(page)

    assert {call.args[0] for call in cdp.on.call_args_list} == {
        "Network.requestWillBeSent",
        "Network.responseReceived",
        "Network.loadingFailed",
    }
