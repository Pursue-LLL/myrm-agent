"""libcurl (curl_cffi) dials the host a canonical URL names.

A URL is judged and dialed in its canonical spelling (``utils.url_syntax``), so the host a policy classifies is the host
a client connects to only if the client reads that spelling the way the canonicalizer does. libcurl is asked about every
spelling in ``DIAL_SPELLINGS``: a resolve entry sends the canonical name to the loopback listener, so the Host header the
listener receives is the host libcurl derived from the URL. The same spellings are also dialed as written, which shows
where a hop that is still dialed as written would be read differently. IPv6 literals are left out because the listener
only speaks IPv4.
"""

from __future__ import annotations

import ipaddress

import pytest
from curl_cffi import CurlOpt, requests
from curl_cffi.requests.exceptions import InvalidURL, RequestException

from myrm_agent_harness.utils.url_syntax import parse_outbound_url
from tests.support.dial_probe import (
    KEEPS_THE_TRAILING_DOT,
    REFUSES_IT,
    Dial,
    HostRecorder,
    Sent,
    host_recorder,
    misdialed_canonical_urls,
    readings_that_differ,
)
from tests.support.host_spellings import DIAL_SPELLINGS

_TIMEOUT_S = 3
_LOOPBACK = "127.0.0.1"

# Where libcurl reads a spelling as written differently from the canonicalizer; every other spelling is the same host.
_DIFFERENT_AS_WRITTEN = {
    "example.test.": KEEPS_THE_TRAILING_DOT,
    "Example.Test.": KEEPS_THE_TRAILING_DOT,
    "localhost.": KEEPS_THE_TRAILING_DOT,
    "٣.test": REFUSES_IT,
    "a.٣": REFUSES_IT,
    "[example.test]": REFUSES_IT,
    "[v1.x]": REFUSES_IT,
}


def _is_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _dial(recorder: HostRecorder, url: str, path: str, canonical_host: str) -> Sent:
    """Request ``url`` the way libcurl reads it.

    Only the canonical name resolves, so a name libcurl derives differently cannot reach the listener unless it is
    the canonical name with or without its trailing dot. A numeric host needs no entry and libcurl writes it into the
    Host header as written, so for it the observation is the address the listener accepted the connection on.
    """
    options: dict[CurlOpt, bytes | list[bytes]] = {CurlOpt.NOPROXY: b"*"}
    numeric = _is_address(canonical_host)
    if not numeric:
        names = (canonical_host, f"{canonical_host}.")
        options[CurlOpt.RESOLVE] = [f"+{name}:{recorder.port}:{_LOOPBACK}".encode() for name in names]
    try:
        requests.get(url, curl_options=options, timeout=_TIMEOUT_S, impersonate=None)
    except InvalidURL:
        return Sent(refused=True)
    except RequestException:
        return Sent()
    host = recorder.host_sent(path)
    return Sent(_LOOPBACK if numeric and host is not None else host)


@pytest.fixture(scope="module")
def dials() -> list[Dial]:
    results: list[Dial] = []
    with host_recorder() as recorder:
        for index, spelling in enumerate(DIAL_SPELLINGS):
            target, error = parse_outbound_url(f"http://{spelling}:{recorder.port}/c{index}")
            assert target is not None, f"{spelling!r} has no canonical spelling ({error}): drop it"
            if ":" in target.hostname:
                continue
            results.append(
                Dial(
                    spelling,
                    target.hostname,
                    _dial(recorder, target.url, f"/c{index}", target.hostname),
                    _dial(recorder, f"http://{spelling}:{recorder.port}/w{index}", f"/w{index}", target.hostname),
                )
            )
    return results


def test_libcurl_dials_the_canonical_host_of_every_canonical_url(dials: list[Dial]) -> None:
    assert len(dials) > len(DIAL_SPELLINGS) // 2
    assert misdialed_canonical_urls(dials) == {}


def test_libcurl_reads_a_spelling_as_written_the_way_the_canonicalizer_does_except_where_declared(
    dials: list[Dial],
) -> None:
    assert readings_that_differ(dials) == _DIFFERENT_AS_WRITTEN
