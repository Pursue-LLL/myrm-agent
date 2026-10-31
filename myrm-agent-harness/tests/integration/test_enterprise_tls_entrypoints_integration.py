"""The enterprise network compatibility setting reaches the client libraries that do not go through httpx.

[INPUT]
- infra.tls_compat::apply_global_tls_relaxation (POS: Enterprise TLS compatibility)
- tests.support.tls_loopback::https_server, connect_proxy, restore_standard_tls (POS: Loopback peers, clean TLS slate)
- tests.support.mcp_testkit.tls_pki::generate_inspection_chain (POS: Server chain shaped like a TLS-inspection proxy's)

[OUTPUT]
- Fails when the setting stops reaching ``urllib.request``, ``http.client``, aiohttp's default session or ``requests``
  (the Feishu long connection, the Feishu QR registration, the Discord and Matrix adapters): a chain issued by an
  inspection-proxy CA (``basicConstraints`` not critical) must be accepted once the setting is on and the environment
  names the CA, and rejected in every other combination.
- Fails when the setting weakens verification on any of them: an unknown CA, an expired certificate and a certificate
  for another host are all still rejected with the setting on.
- Fails when ``requests`` stops honouring the setting through a ``CONNECT`` proxy, or stops honouring a pinned CA.
- Fails when switching the setting off stops relaxing the contexts the standard library builds afterwards.

[POS]
Real-stack drift guard for ``infra/tls_compat.py`` next to ``test_enterprise_tls_compat_integration.py`` (httpx and the
chat model). Each library builds its context through a different entry point (``ssl._create_default_https_context``,
aiohttp's import-time default, urllib3's own builder), so each is exercised against a loopback HTTPS listener whose
chain strict OpenSSL verification rejects.
"""

from __future__ import annotations

import asyncio
import http.client
import ssl
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
import pytest
import requests

from myrm_agent_harness.infra.tls_compat import apply_global_tls_relaxation
from tests.support.mcp_testkit.tls_pki import InspectionChain, generate_inspection_chain
from tests.support.tls_loopback import (
    CA_ENV_VARS,
    connect_proxy,
    https_server,
    isolate_from_system_proxy,
    restore_standard_tls,
)

_TIMEOUT = 10
_STDLIB_STACKS = ("urllib", "http_client")
_STACKS = (*_STDLIB_STACKS, "aiohttp", "requests")

pytestmark = pytest.mark.skipif(
    not getattr(ssl, "VERIFY_X509_STRICT", 0), reason="VERIFY_X509_STRICT not available (Python < 3.13)"
)


@pytest.fixture(autouse=True)
def _pristine_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    restore_standard_tls(monkeypatch)
    isolate_from_system_proxy(monkeypatch)


@pytest.fixture
def chain(tmp_path: Path) -> InspectionChain:
    return generate_inspection_chain(tmp_path)


def _enterprise_mode(
    monkeypatch: pytest.MonkeyPatch, *, ca_env: str | None = None, ca_file: Path | None = None
) -> None:
    """What a host does at startup when the setting is on: set the toggle, name a CA, install the policy."""
    monkeypatch.setenv("MYRM_TLS_STRICT", "0")
    if ca_env is not None and ca_file is not None:
        monkeypatch.setenv(ca_env, str(ca_file))
    assert apply_global_tls_relaxation() is True


def _get_with_urllib(url: str) -> None:
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as response:  # noqa: S310 - loopback URL built by the test
        assert response.status == 200


def _get_with_http_client(url: str) -> None:
    target = urlsplit(url)
    connection = http.client.HTTPSConnection(target.hostname or "", target.port, timeout=_TIMEOUT)
    try:
        connection.request("GET", "/")
        assert connection.getresponse().status == 200
    finally:
        connection.close()


def _get_with_requests(url: str) -> None:
    requests.get(url, timeout=_TIMEOUT).raise_for_status()


_BLOCKING_STACKS: dict[str, Callable[[str], None]] = {
    "urllib": _get_with_urllib,
    "http_client": _get_with_http_client,
    "requests": _get_with_requests,
}


async def _call(stack: str, url: str) -> None:
    if stack == "aiohttp":
        async with aiohttp.ClientSession(trust_env=False) as session, session.get(url) as response:
            assert response.status == 200
        return
    await asyncio.to_thread(_BLOCKING_STACKS[stack], url)


def _certificate_verdicts(error: BaseException | None) -> bool:
    """Whether *error* or anything it wraps is the standard library's certificate-verification failure."""
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ssl.SSLCertVerificationError):
            return True
        wrapped = getattr(error, "certificate_error", None) or getattr(error, "reason", None)
        if isinstance(wrapped, BaseException) and _certificate_verdicts(wrapped):
            return True
        error = error.__cause__ or error.__context__
    return False


async def _assert_rejected_as_certificate(stack: str, url: str) -> None:
    with pytest.raises(Exception) as rejected:
        await _call(stack, url)
    assert _certificate_verdicts(rejected.value), repr(rejected.value)


@pytest.mark.parametrize("stack", _STACKS)
async def test_strict_verification_rejects_the_inspection_chain_by_default(stack: str, chain: InspectionChain) -> None:
    with https_server(chain) as url:
        await _assert_rejected_as_certificate(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
async def test_the_setting_without_a_ca_does_not_trust_an_unknown_issuer(
    stack: str, chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enterprise_mode(monkeypatch)

    with https_server(chain) as url:
        await _assert_rejected_as_certificate(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
@pytest.mark.parametrize("ca_env", CA_ENV_VARS)
async def test_a_named_ca_without_the_setting_is_not_trusted(
    stack: str, ca_env: str, chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ca_env, str(chain.ca_cert))
    assert apply_global_tls_relaxation() is False

    with https_server(chain) as url:
        await _assert_rejected_as_certificate(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
@pytest.mark.parametrize("ca_env", CA_ENV_VARS)
async def test_the_setting_with_a_named_ca_accepts_the_inspection_chain(
    stack: str, ca_env: str, chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enterprise_mode(monkeypatch, ca_env=ca_env, ca_file=chain.ca_cert)

    with https_server(chain) as url:
        await _call(stack, url)


@pytest.mark.parametrize("stack", _STACKS)
@pytest.mark.parametrize(
    ("server_names", "expired"),
    [(("127.0.0.1", "localhost"), True), (("other.example",), False)],
    ids=["expired", "other_host"],
)
async def test_the_setting_still_rejects_an_expired_certificate_and_one_for_another_host(
    stack: str,
    server_names: tuple[str, ...],
    expired: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flawed = generate_inspection_chain(tmp_path, server_names=server_names, expired=expired)
    _enterprise_mode(monkeypatch, ca_env="NODE_EXTRA_CA_CERTS", ca_file=flawed.ca_cert)

    with https_server(flawed) as url:
        await _assert_rejected_as_certificate(stack, url)


@pytest.mark.parametrize("stack", _STDLIB_STACKS)
async def test_switching_the_setting_off_stops_relaxing_new_standard_library_contexts(
    stack: str, chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enterprise_mode(monkeypatch, ca_env="NODE_EXTRA_CA_CERTS", ca_file=chain.ca_cert)
    monkeypatch.delenv("MYRM_TLS_STRICT")

    with https_server(chain) as url:
        await _assert_rejected_as_certificate(stack, url)


async def test_requests_honours_a_pinned_ca_bundle_under_the_setting(
    chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enterprise_mode(monkeypatch)

    with https_server(chain) as url:
        await asyncio.to_thread(requests.get, url, timeout=_TIMEOUT, verify=str(chain.ca_cert))


async def test_requests_rejects_the_inspection_chain_with_a_pinned_ca_bundle_while_strict(
    chain: InspectionChain,
) -> None:
    with https_server(chain) as url, pytest.raises(requests.exceptions.SSLError):
        await asyncio.to_thread(requests.get, url, timeout=_TIMEOUT, verify=str(chain.ca_cert))


async def test_requests_through_a_connect_proxy_accepts_the_inspection_chain_under_the_setting(
    chain: InspectionChain, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enterprise_mode(monkeypatch, ca_env="REQUESTS_CA_BUNDLE", ca_file=chain.ca_cert)

    with https_server(chain) as url, connect_proxy() as proxy:
        await asyncio.to_thread(requests.get, url, timeout=_TIMEOUT, proxies={"https": proxy.url})
        assert proxy.tunnels == [urlsplit(url).netloc]


async def test_requests_through_a_connect_proxy_rejects_the_inspection_chain_while_strict(
    chain: InspectionChain,
) -> None:
    with https_server(chain) as url, connect_proxy() as proxy:
        with pytest.raises(requests.exceptions.SSLError):
            await asyncio.to_thread(requests.get, url, timeout=_TIMEOUT, proxies={"https": proxy.url})
        assert proxy.tunnels == [urlsplit(url).netloc]
