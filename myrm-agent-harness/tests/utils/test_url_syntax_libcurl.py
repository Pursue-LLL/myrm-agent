"""libcurl (curl_cffi) dials the host a canonical URL names.

The HTTP tier requests every hop in its canonical spelling (``utils.url_syntax``), so the host a policy classifies is the
host libcurl connects to only if libcurl reads that spelling the way the canonicalizer does. libcurl is asked about every
spelling in ``DIAL_SPELLINGS``: a resolve entry sends the canonical name to the loopback listener, so the Host header the
listener receives is the host libcurl derived from the URL. The IDN library behind libcurl (AppleIDN, libidn2, WinIDN)
differs between platforms, so the test runs wherever the unit tests do. IPv6 literals are left out because the listener
only speaks IPv4.
"""

from __future__ import annotations

import ipaddress

import pytest
from curl_cffi import CurlOpt, requests
from curl_cffi.requests.exceptions import InvalidURL, RequestException

from myrm_agent_harness.utils.url_syntax import parse_outbound_url
from tests.support.dial_probe import Dial, HostRecorder, Sent, host_recorder, misdialed_canonical_urls
from tests.support.host_spellings import DIAL_SPELLINGS

_TIMEOUT_S = 3
_LOOPBACK = "127.0.0.1"


def _is_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _dial(recorder: HostRecorder, url: str, path: str, canonical_host: str) -> Sent:
    """Request ``url`` the way libcurl reads it.

    Only the canonical name resolves, so a name libcurl derives differently cannot reach the listener. A numeric host
    needs no entry and libcurl writes it into the Host header as written, so for it the observation is the address the
    listener accepted the connection on.
    """
    options: dict[CurlOpt, bytes | list[bytes]] = {CurlOpt.NOPROXY: b"*"}
    numeric = _is_address(canonical_host)
    if not numeric:
        options[CurlOpt.RESOLVE] = [f"+{canonical_host}:{recorder.port}:{_LOOPBACK}".encode()]
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
            results.append(Dial(spelling, target.hostname, _dial(recorder, target.url, f"/c{index}", target.hostname)))
    return results


def test_libcurl_dials_the_canonical_host_of_every_canonical_url(dials: list[Dial]) -> None:
    assert len(dials) > len(DIAL_SPELLINGS) // 2
    assert misdialed_canonical_urls(dials) == {}
