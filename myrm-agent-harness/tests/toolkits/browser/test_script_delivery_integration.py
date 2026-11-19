"""Real-Chromium proof that the page scripts of a pooled context reach every document the browser loads.

A pooled context delivers four scripts: the DOM enhancer (every context), the stealth script (STEALTH contexts) and the
CSP and hardening scripts of a domain allowlist. The HTTPS site presents a certificate from a private CA that the
browser accepts (its public key is on the launch flag) and that the driver, which keeps its own trust store, does not.
A delivery that needed the driver to fetch each page itself would lose the scripts on a GET and refuse the form POST.
Each scenario reads, from the page's own first script, which of the scripts had already run: a script that arrives
later cannot stop a request the page starts first. Run with:
`pytest -m integration tests/toolkits/browser/test_script_delivery_integration.py`.
"""

from __future__ import annotations

import base64
import hashlib
import html
import ssl
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist
from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.pool.browser_pool import _DEFAULT_LAUNCH_OPTIONS
from myrm_agent_harness.toolkits.browser.utils.private_origins import private_origin_grants
from tests.support.mcp_testkit.tls_pki import generate_tls_pki
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._redirect_servers import Reply, Site, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_MAIN_WORLD = {"isolated_context": False}
_TIMEOUT_MS = 15_000

# What the first script of a page's head sees. ``violations`` collects the CSP verdicts; the fetch to a host outside the
# allowlist is stopped by the policy only when the policy is already in force, otherwise the HTTP filter stops it and
# no violation is reported.
_RTC_STATE = "(function () { try { new RTCPeerConnection(); return 'open'; } catch (e) { return 'blocked'; } })()"
_PROBE_SCRIPT = f"""
window.__probe = {{
  enhancer: window.__myrm_enhancer_initialized === true,
  stealth: EventTarget.prototype.__vx_stealth_applied === true,
  rtc: {_RTC_STATE},
  violations: [],
}};
document.addEventListener('securitypolicyviolation', function (e) {{ window.__probe.violations.push(e.violatedDirective); }});
fetch('https://blocked.invalid/x', {{mode: 'no-cors'}}).catch(function () {{}});
"""
_FORM = '<form method="post" action="/order"><button id="go">go</button></form>'
_RTC_ONLY_PROBE = f"window.__probe = {{rtc: {_RTC_STATE}}};"


def _document(body: str = "", script: str = _PROBE_SCRIPT) -> Reply:
    return Reply(body=f"<!DOCTYPE html><html><head><script>{script}</script></head><body>{body}</body></html>".encode())


def _frames_page() -> Reply:
    inline = html.escape(f"<script>{_RTC_ONLY_PROBE}</script>", quote=True)
    return _document(f'<iframe name="same" src="/"></iframe><iframe name="inline" srcdoc="{inline}"></iframe>')


def _expected(*, stealth: bool) -> dict[str, object]:
    """Every script ran before the page's own: enhancer present, RTC hardened, CSP refusing the foreign fetch."""
    return {"enhancer": True, "stealth": stealth, "rtc": "blocked", "violations": ["connect-src"]}


def _public_key_pin(certificate: Path) -> str:
    """The base64 SHA-256 of the certificate's public key, the form Chromium's ``--ignore-certificate-errors-spki-list`` reads."""
    leaf = x509.load_pem_x509_certificate(certificate.read_bytes())
    key = leaf.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(hashlib.sha256(key).digest()).decode()


@pytest.fixture
def site_and_pin(tmp_path: Path) -> Iterator[tuple[Site, str]]:
    """An HTTPS loopback site the browser accepts and the driver does not, and the pin that makes the browser accept it."""
    pki = generate_tls_pki(tmp_path)
    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.load_cert_chain(pki.server_cert, pki.server_key)
    routes = {
        "/": _document("probe"),
        "/form": _document(_FORM),
        "/order": _document("receipt"),
        "/frames": _frames_page(),
    }
    with serve(routes, tls=server_tls) as site:
        yield site, _public_key_pin(pki.server_cert)


@asynccontextmanager
async def _tab(site: Site, pin: str, context_type: ContextType) -> AsyncIterator[Page]:
    """A tab in a context of the pool, as production builds it: a domain allowlist holding the site, certificates verified."""
    default_args = _DEFAULT_LAUNCH_OPTIONS["args"]
    assert isinstance(default_args, list)
    launch_options = {
        **_DEFAULT_LAUNCH_OPTIONS,
        "args": [*default_args, f"--ignore-certificate-errors-spki-list={pin}"],
    }
    pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal(), launch_options=launch_options)
    allowlist = DomainAllowlist.from_strings(("127.0.0.1",))
    tab, context_key = await pool.acquire_page(
        context_type, context_kwargs={"domain_allowlist": allowlist, "allow_private_networks": True}
    )
    private_origin_grants(tab.context).grant(site.base_url)
    try:
        yield tab
    finally:
        await pool.release_page(tab, context_key)
        await pool.shutdown()


@pytest.mark.parametrize("context_type", [ContextType.AGENT, ContextType.STEALTH])
async def test_get_document_has_every_script_before_its_own(
    site_and_pin: tuple[Site, str], context_type: ContextType
) -> None:
    site, pin = site_and_pin
    async with _tab(site, pin, context_type) as tab:
        await tab.goto(site.url("/"), timeout=_TIMEOUT_MS)
        assert await tab.evaluate("window.__probe", **_MAIN_WORLD) == _expected(
            stealth=context_type is ContextType.STEALTH
        )


async def test_form_post_is_sent_once_and_its_answer_has_every_script(site_and_pin: tuple[Site, str]) -> None:
    site, pin = site_and_pin
    async with _tab(site, pin, ContextType.AGENT) as tab:
        await tab.goto(site.url("/form"), timeout=_TIMEOUT_MS)
        async with tab.expect_navigation(timeout=_TIMEOUT_MS):
            await tab.click("#go", timeout=_TIMEOUT_MS)
        assert await tab.inner_text("body") == "receipt"
        assert await tab.evaluate("window.__probe", **_MAIN_WORLD) == _expected(stealth=False)
    assert site.paths("POST") == ["/order"]


async def test_same_origin_frames_have_the_scripts(site_and_pin: tuple[Site, str]) -> None:
    site, pin = site_and_pin
    async with _tab(site, pin, ContextType.AGENT) as tab:
        await tab.goto(site.url("/frames"), timeout=_TIMEOUT_MS)
        frames = {frame.name: frame for frame in tab.frames if frame.name}
        assert await frames["same"].evaluate("window.__probe", **_MAIN_WORLD) == _expected(stealth=False)
        assert await frames["inline"].evaluate("window.__probe", **_MAIN_WORLD) == {"rtc": "blocked"}


async def test_popup_of_the_same_origin_keeps_the_global_hardening(site_and_pin: tuple[Site, str]) -> None:
    """The first document of such a popup reuses the opener's window, so scripts that set globals stay in force."""
    site, pin = site_and_pin
    async with _tab(site, pin, ContextType.AGENT) as tab:
        await tab.goto(site.url("/"), timeout=_TIMEOUT_MS)
        async with tab.context.expect_page(timeout=_TIMEOUT_MS) as popup_info:
            await tab.evaluate("window.open('/')", **_MAIN_WORLD)
        popup = await popup_info.value
        await popup.wait_for_load_state("load", timeout=_TIMEOUT_MS)
        assert await popup.evaluate(_RTC_STATE, **_MAIN_WORLD) == "blocked"
