"""URL policy for one web_fetch request: the SSRF guard and the user's network blocklist.

[INPUT]
- core.security.guards.ssrf::async_pin_url, SSRFSecurityError (POS: DNS-validated URL checks + audit)
- core.security.guards.url_allowlist::URLAllowlistGuard (POS: skill DLP domain allowlist)
- core.security.redirect_hop_guard::RedirectHopEvaluator, PrivateOriginGrants (POS: private network and cloud metadata classification; local mode also judges a hostname by what it resolves to)
- core.security.domain_match::host_matches (POS: the host matcher the permission engine and the browser domain filter share)
- core.security.audit::record_decision (POS: security decision audit trail)
- utils.url_syntax::parse_outbound_url (POS: the canonical spelling of an outbound URL, or why it has none; no hostname blocklist)

[OUTPUT]
- FetchTargetGuard: judges, canonicalizes and pins every URL one fetch contacts (the requested URL and each redirect hop)
- NetworkBlocklistError: the terminal verdict for a URL whose host is on the network blocklist
- assert_not_blocklisted(): the blocklist verdict for one URL, for the callers that judge a single URL

[POS]
Per-fetch URL policy for the web_fetch tiers. The network blocklist is the user's list of hosts the agent
must not read; it holds for every page a fetch returns, so a listed host cannot be read by being the target
of a redirect: the HTTP tier judges each hop before requesting it, the browser tiers the URL they were given and
the page they ended on. It is judged first and needs no DNS, and it applies whether or not
the SSRF shield is on.

The SSRF policy of the tiers that follow redirects: cloud policy resolves the host and requires every
address to be public. Local policy (``allow_private_networks``) classifies the host as written and by its
DNS answer, but only loopback, link-local and metadata answers count: the user's own resolver is not
otherwise second-guessed, the origin the fetch was aimed at may be private, any other private origin
reached through a redirect may not, and cloud metadata endpoints never may. Exact hosts listed in
``MYRM_ALLOWED_INTERNAL_HOSTS`` stay reachable under both policies. ``canonical_url`` gives the spelling a
hop is judged and dialed in, so a legacy-spelled address or a Unicode host is the host the client connects
to, and a URL with no canonical spelling is refused.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.audit import record_decision
from myrm_agent_harness.core.security.domain_match import host_matches
from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError, async_pin_url
from myrm_agent_harness.core.security.guards.url_allowlist import URLAllowlistGuard
from myrm_agent_harness.core.security.redirect_hop_guard import (
    HopDisposition,
    PrivateOriginGrants,
    RedirectHopEvaluator,
)
from myrm_agent_harness.utils.url_syntax import OutboundUrl, parse_outbound_url

logger = logging.getLogger(__name__)


class NetworkBlocklistError(SSRFSecurityError):
    """A URL names a host on the network blocklist.

    A subclass of ``SSRFSecurityError`` so every tier and the engine treat it as the same terminal verdict:
    the fetch fails, no other tier tries the URL, and the failure is remembered.
    """


def assert_not_blocklisted(url: str, network_blocklist: tuple[str, ...]) -> None:
    """Raise ``NetworkBlocklistError`` when *url* names a host on *network_blocklist*; an empty list admits every URL.

    A URL with no canonical spelling cannot be judged against the list, so it raises ``SSRFSecurityError``.
    """
    if not network_blocklist:
        return
    target, error = parse_outbound_url(url)
    if target is None:
        raise SSRFSecurityError(error)
    if host_matches(target.hostname, network_blocklist):
        reason = f"Domain '{target.hostname}' is blocked by policy"
        record_decision("web_fetch", "DENY", reason)
        raise NetworkBlocklistError(reason)


class FetchTargetGuard:
    """Guard bound to one fetch; its methods raise ``SSRFSecurityError`` for a URL the policy rejects."""

    def __init__(
        self,
        *,
        requested_url: str,
        allow_private_networks: bool,
        allowed_hosts: list[str],
        ssrf_shield: bool,
        network_blocklist: tuple[str, ...],
    ) -> None:
        self._allowed_hosts = allowed_hosts
        self._ssrf_shield = ssrf_shield
        self._network_blocklist = network_blocklist
        self._local_policy: RedirectHopEvaluator | None = None
        if allow_private_networks:
            grants = PrivateOriginGrants()
            requested, _ = parse_outbound_url(requested_url)
            if requested is not None:
                grants.grant(requested.url)
            self._local_policy = RedirectHopEvaluator(grants=grants)

    @classmethod
    def for_fetch(
        cls,
        requested_url: str,
        *,
        allow_private_networks: bool,
        allowed_hosts: list[str],
        ssrf_shield: bool,
        network_blocklist: tuple[str, ...],
    ) -> FetchTargetGuard | None:
        """The guard a fetch needs, or ``None`` when neither the SSRF shield nor a blocklist applies to it."""
        if not ssrf_shield and not network_blocklist:
            return None
        return cls(
            requested_url=requested_url,
            allow_private_networks=allow_private_networks,
            allowed_hosts=allowed_hosts,
            ssrf_shield=ssrf_shield,
            network_blocklist=network_blocklist,
        )

    def canonical_url(self, url: str) -> str:
        """The spelling a URL is judged and dialed in: pass it to ``pin``, then request what ``pin`` returns."""
        return self._canonical_target(url).url

    @staticmethod
    def _canonical_target(url: str) -> OutboundUrl:
        target, error = parse_outbound_url(url)
        if target is None:
            raise SSRFSecurityError(error)
        return target

    async def pin(self, url: str) -> tuple[str, dict[str, str]]:
        """Return the URL to request and the extra headers it needs (DNS-pinned under the cloud policy)."""
        assert_not_blocklisted(url, self._network_blocklist)
        if not self._ssrf_shield:
            return url, {}
        if self._local_policy is None:
            return await async_pin_url(url, self._allowed_hosts)

        target = self._canonical_target(url)
        URLAllowlistGuard.check(target.hostname)
        if target.hostname not in self._allowed_hosts:
            verdict = await self._local_policy.evaluate_hop_resolved(target.url)
            if verdict.disposition != HopDisposition.ALLOW:
                logger.warning("SSRF blocked request: %s — %s", url, verdict.reason)
                record_decision("ssrf", "SSRF_BLOCKED", f"{url}: {verdict.reason}")
                raise SSRFSecurityError(f"Access to internal network is blocked for security reasons. {verdict.reason}")
        return url, {}
