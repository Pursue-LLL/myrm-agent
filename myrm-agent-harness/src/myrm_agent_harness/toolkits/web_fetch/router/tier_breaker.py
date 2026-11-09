"""Per-domain tier breaker: stop starting a crawl on a fetch tier that a higher tier keeps making up for.

A tier is blamed for a failure only once a higher tier then succeeds on the same domain: that contrast shows the tier
itself is what fails. Counting failures alone cannot tell it from a network outage or a slow site, which would pin a
healthy domain to a slower tier for good. An open tier is retried on every ``probe_every``-th visit, and one success
closes it. STEALTH is the last tier and is never skipped.

[INPUT]
- web_fetch.fetchers.protocols::FetcherType (POS: Fetch tier identifiers)

[OUTPUT]
- TierBreaker: start-tier selection and outcome reporting per domain
- get_global_tier_breaker: process-wide shared TierBreaker

[POS]
Start-tier policy of the layered fetch engine. In-memory, per process; domains are tracked only while a tier is failing.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

from ..fetchers.protocols import FetcherType

logger = logging.getLogger(__name__)

_TIER_ORDER = (FetcherType.HTTP, FetcherType.BROWSER, FetcherType.STEALTH)
# STEALTH is the last resort, so only the tiers below it can be skipped.
_SKIPPABLE_TIERS = _TIER_ORDER[:-1]

_OPEN_AFTER = 3
_PROBE_EVERY = 10
_MAX_DOMAINS = 4096


@dataclass(slots=True)
class _TierState:
    blamed: int = 0
    """Failures that a higher tier then made up for."""
    pending: bool = False
    """Failed since the last contrast, so the next success of a higher tier blames it."""
    skipped: int = 0
    """Visits that bypassed this tier while it was open."""


class TierBreaker:
    """Decides, per domain, which tier a crawl starts on. Thread-safe."""

    def __init__(
        self,
        *,
        open_after: int = _OPEN_AFTER,
        probe_every: int = _PROBE_EVERY,
        max_domains: int = _MAX_DOMAINS,
    ) -> None:
        self._open_after = open_after
        self._probe_every = probe_every
        self._max_domains = max_domains
        self._lock = threading.Lock()
        self._domains: OrderedDict[str, dict[FetcherType, _TierState]] = OrderedDict()

    def select(self, domain: str) -> FetcherType:
        """Return the tier a crawl of ``domain`` starts on."""
        with self._lock:
            tiers = self._domains.get(domain)
            if not tiers:
                return FetcherType.HTTP
            self._domains.move_to_end(domain)
            for tier in _SKIPPABLE_TIERS:
                state = tiers.get(tier)
                if state is None or state.blamed < self._open_after:
                    return tier
                state.skipped += 1
                if state.skipped % self._probe_every == 0:
                    return tier
            return FetcherType.STEALTH

    def report(self, domain: str, tier: FetcherType, *, success: bool) -> None:
        """Record the outcome of a real attempt of ``tier`` on ``domain``."""
        with self._lock:
            if success:
                self._record_success(domain, tier)
            elif tier in _SKIPPABLE_TIERS:
                self._record_failure(domain, tier)

    def _record_success(self, domain: str, tier: FetcherType) -> None:
        tiers = self._domains.get(domain)
        if tiers is None:
            return
        for lower in _SKIPPABLE_TIERS[: _TIER_ORDER.index(tier)]:
            state = tiers.get(lower)
            if state is not None and state.pending:
                state.pending = False
                state.blamed += 1
                if state.blamed == self._open_after:
                    logger.warning(
                        "Tier breaker opened: %s is skipped for %s (a higher tier succeeded after %d failures)",
                        lower.name,
                        domain,
                        state.blamed,
                    )
        # The success proves the tier works here, which clears any failure another request left pending.
        recovered = tiers.pop(tier, None)
        if recovered is not None and recovered.blamed >= self._open_after:
            logger.info("Tier breaker closed: %s works again for %s", tier.name, domain)
        if not tiers:
            del self._domains[domain]

    def _record_failure(self, domain: str, tier: FetcherType) -> None:
        tiers = self._domains.get(domain)
        if tiers is None:
            tiers = self._domains[domain] = {}
            while len(self._domains) > self._max_domains:
                self._domains.popitem(last=False)
        else:
            self._domains.move_to_end(domain)
        tiers.setdefault(tier, _TierState()).pending = True


_global_tier_breaker: TierBreaker | None = None


def get_global_tier_breaker() -> TierBreaker:
    """Get the process-wide tier breaker: engines are created per call, what a domain taught must outlive them."""
    global _global_tier_breaker
    if _global_tier_breaker is None:
        _global_tier_breaker = TierBreaker()
    return _global_tier_breaker
