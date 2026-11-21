"""Domain deep filtering — four-layer defense-in-depth for browser network egress.

Prevents pages from exfiltrating data through the channels that bypass Playwright's
``context.route()``: WebSocket, WebRTC and WebTransport.

Architecture
~~~~~~~~~~~~

Layer 0 — CSP Core Defense (``<meta http-equiv="Content-Security-Policy">``, delivered by an init script)
    Browser-native policy enforcement via Content Security Policy.
    Restricts the document's own network connections (fetch/XHR/WebSocket/EventSource/sendBeacon) and
    script/iframe loading; a ``blob:`` or ``data:`` Worker is refused (``worker-src`` falls back to ``script-src``).
    A Worker started from a URL answers to its own response's policy, so Layer 1 is what stops its HTTP requests
    and a WebSocket it opens itself is judged by none of the layers.
    Does NOT restrict img/style/font/media (allows CDN resources for compatibility).
    A policy ``<meta>`` is enforced only inside the head, so an XML or SVG document, which has a root element but no
    head, is given one.
    The policy is document-scoped, and the first document of a same-origin popup opened with ``window.open`` normally
    gets no init-script run of its own: it reuses the popup's initial window. The script therefore wraps the WebSocket,
    Worker and SharedWorker constructors, which puts the policy on the current document before the browser runs one.
    A popup that keeps its opener can run its first script before Layers 0 and 2 (``BROWSER_SYSTEM.md`` section 10).

Layer 1 — Protocol Interception (``context.route('**/*')``)
    Hard-blocks all HTTP/HTTPS requests to non-allowed domains (fetch, XHR, EventSource and sendBeacon included),
    in every document of the context, a popup's first one too.
    Supports resource type filtering (image/stylesheet/script/font/media); fallback defense if CSP is disabled.

Layer 2 — Main Thread Hardening (init script)
    Hardens RTCPeerConnection and WebTransport (not covered by CSP).
    Disables Service Worker registration (offline cache not needed for agents).
    Does NOT harden Web Workers to avoid anti-bot detection; Layer 0 only wraps their constructors.
    Window-global, so it also holds in a reused popup window.

Layer 3 — CDP Audit Monitor (``Network.webSocketCreated``)
    Detects WebSocket connections of page targets at the Chrome DevTools Protocol level.
    Does not block — provides audit visibility for all layers.

The init scripts of Layers 0 and 2 run in the page's main world. The agent's own JavaScript runs in the driver's
isolated world on the default engine, where neither is present, and in the main world on stock Playwright (Camoufox).
``agent_world`` (called by ``BrowserSession.evaluate``, not re-exported) runs the same two scripts in whichever world
the expression runs in, once per window, so an expression gets the policy and the hardening on both
(``BROWSER_SYSTEM.md`` section 10).


[INPUT]
- pool.config::ResourceBlockConfig (POS: resource blocking config, includes block_ad_domains flag)
- .ad_domains::AD_DOMAINS (POS: frozenset of ~3500 ad/tracker domains, lazy-loaded when block_ad_domains=True)
- core.security.domain_match::canonical_entry, host_matches (POS: one reading of the domain entries of a network list)
- .scripts::build_csp_meta_script, build_init_script (POS: the CSP and hardening init scripts the installer registers)

[OUTPUT]
- DomainAllowlist: immutable domain pattern matcher
- install_domain_filter: async installer for all four layers with resource blocking
- build_csp_meta_script, build_init_script: re-exported page-side scripts of Layers 0 and 2

[POS]
Deep domain filtering, resource blocking, and ad/tracker domain blocking module for the browser toolkit, called by
ContextFactory during context creation. Layer 1 judges every HTTP(S) request of the context and applies resource type
blocking (image/stylesheet/script/font/media) and the ad/tracker domain blocklist (~3500 domains via ad_domains.py);
Layers 0 and 2 cover what it cannot see (WebSocket, Workers started from a blob or data URL, WebRTC, WebTransport and
Service Worker registration).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from patchright.async_api import BrowserContext, Page

    from myrm_agent_harness.toolkits.browser.pool.config import ResourceBlockConfig

from myrm_agent_harness.core.security.domain_match import canonical_entry, host_matches
from myrm_agent_harness.toolkits.browser.domain_filter.http_filter import (
    _RESOURCE_TYPE_MAP,
)
from myrm_agent_harness.toolkits.browser.domain_filter.http_filter import (
    install_http_filter as _install_http_filter,
)
from myrm_agent_harness.toolkits.browser.domain_filter.scripts import build_csp_meta_script, build_init_script

__all__ = [
    "DomainAllowlist",
    "DomainBlocklist",
    "build_csp_meta_script",
    "build_init_script",
    "install_domain_filter",
]

# Strong references to fire-and-forget CDP audit tasks. Without a reference the
# task can be garbage-collected mid-flight (e.g. when the event loop closes
# while a mock/attached CDP session is being awaited), producing a
# "coroutine never awaited" RuntimeWarning on shutdown.
_cdp_audit_tasks: set[asyncio.Task[None]] = set()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core data structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DomainAllowlist:
    """Immutable domain allowlist with exact and wildcard matching.

    Entries are read by ``core.security.domain_match``, the same reading the permission engine uses:
    - ``"example.com"`` — exact match
    - ``"*.example.com"`` and ``".example.com"`` — match ``example.com`` and all subdomains
    - Punycode (IDN) conversion and URL cleaning (scheme/port/path stripping) happen when the list is built.

    Callers with an allowlist semantics use :meth:`is_allowed`; callers with a
    blocklist semantics use :meth:`is_blocked`. Both share the same pattern
    matching — the pair exists so each call site reads in its own terms.
    """

    patterns: tuple[str, ...]

    def is_allowed(self, hostname: str) -> bool:
        """Return True when *hostname* matches an allowed pattern."""
        return host_matches(hostname, self.patterns)

    def is_blocked(self, hostname: str) -> bool:
        """Return True when *hostname* matches a blocked pattern.

        Semantically the mirror of :meth:`is_allowed` — both test pattern
        membership; the distinct name lets blocklist call sites read naturally
        instead of reinterpreting ``is_allowed`` as "is in the deny list".
        """
        return host_matches(hostname, self.patterns)

    @classmethod
    def from_strings(cls, domains: Sequence[str]) -> DomainAllowlist:
        """Create from a sequence of domain pattern strings."""
        cleaned = tuple(canonical_entry(d) for d in domains if d.strip())
        return cls(patterns=tuple(d for d in cleaned if d))

    @property
    def is_empty(self) -> bool:
        return len(self.patterns) == 0


# DomainBlocklist shares the pattern matcher; blocklist call sites use is_blocked().
DomainBlocklist = DomainAllowlist


# ---------------------------------------------------------------------------
# Orchestrator: install all four layers
# ---------------------------------------------------------------------------


async def install_domain_filter(
    context: BrowserContext,
    allowlist: DomainAllowlist,
    *,
    domain_blocklist: DomainBlocklist | None = None,
    enable_cdp_audit: bool = True,
    resource_block: ResourceBlockConfig | None = None,
    allow_private_networks: bool = False,
) -> None:
    """Install four-layer domain filtering on a BrowserContext.

    Does nothing if *allowlist* is empty, *domain_blocklist* is empty, and no resource blocking is configured.

    Args:
        context: Patchright BrowserContext to protect.
        allowlist: Domains the page is allowed to connect to.
        domain_blocklist: Domains always blocked (checked before allowlist).
        enable_cdp_audit: Whether to install CDP WebSocket audit monitoring.
        resource_block: Resource blocking configuration (images/css/js/fonts/media/ad-domains).
        allow_private_networks: Let requests reach loopback/private/link-local addresses (local mode).
            Only the private-address and cloud-metadata hop check is skipped; allow/block lists and
            resource rules still apply.
    """
    has_resource_block = False
    if resource_block:
        has_resource_block = any(getattr(resource_block, k) for k in _RESOURCE_TYPE_MAP.values())

    ad_blocklist: frozenset[str] | None = None
    if resource_block and resource_block.block_ad_domains:
        from .ad_domains import AD_DOMAINS

        ad_blocklist = AD_DOMAINS

    if (
        allowlist.is_empty
        and not has_resource_block
        and not ad_blocklist
        and (domain_blocklist is None or domain_blocklist.is_empty)
    ):
        return

    if not allowlist.is_empty:
        await context.add_init_script(build_csp_meta_script(allowlist))
        await context.add_init_script(build_init_script())

    await _install_http_filter(
        context,
        allowlist,
        resource_block,
        ad_blocklist,
        domain_blocklist,
        allow_private_networks=allow_private_networks,
    )

    if enable_cdp_audit and not allowlist.is_empty:
        context.on("page", lambda page: _schedule_cdp_audit(page, allowlist))

    logger.info(
        "Domain filter / Resource block installed: %d allow patterns, %d block patterns, CDP audit=%s, resource_block=%s, ad_blocklist=%d",
        len(allowlist.patterns),
        len(domain_blocklist.patterns) if domain_blocklist else 0,
        enable_cdp_audit and not allowlist.is_empty,
        resource_block is not None,
        len(ad_blocklist) if ad_blocklist else 0,
    )


# ---------------------------------------------------------------------------
# Layer 3: CDP audit monitor
# ---------------------------------------------------------------------------


def _schedule_cdp_audit(page: Page, allowlist: DomainAllowlist) -> None:
    """Schedule CDP audit installation for a new page (non-async callback)."""
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_install_cdp_audit(page, allowlist))
        _cdp_audit_tasks.add(task)

        def _discard(task: asyncio.Task[None]) -> None:
            _cdp_audit_tasks.discard(task)

        task.add_done_callback(_log_task_exception)
        task.add_done_callback(_discard)
    except RuntimeError:
        pass


def _log_task_exception(task: asyncio.Task[None]) -> None:
    """Log unhandled exceptions from fire-and-forget CDP audit tasks."""
    if not task.cancelled() and task.exception():
        logger.warning("CDP audit task failed: %s", task.exception())


async def _install_cdp_audit(page: Page, allowlist: DomainAllowlist) -> None:
    """Listen for WebSocket creation events via CDP and log violations."""
    try:
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Network.enable")

        def _on_ws_created(params: dict[str, object]) -> None:
            url = str(params.get("url", ""))
            hostname = urlparse(url).hostname or ""
            if not allowlist.is_allowed(hostname):
                logger.warning(
                    "SECURITY AUDIT: Unexpected WebSocket connection to non-allowed domain: %s",
                    url,
                )

        cdp.on("Network.webSocketCreated", _on_ws_created)
    except Exception as exc:
        logger.warning("CDP audit monitor setup failed (non-critical): %s", exc)
