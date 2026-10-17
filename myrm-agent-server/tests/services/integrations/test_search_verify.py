"""Tests for the search readiness probe: chain-aware verdict, credential precheck and verdict cache.

The probe runs through the real harness search chain; only the per-provider search client is replaced, keyed by the
provider's API key, so each test scripts exactly what every chain member answers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.web_search.coalescing.search_coalescing import (
    reset_search_coalescing_state_for_tests,
)
from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.providers.chain import default_quota_tracker
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig, WebSearcher

from app.core.channel_bridge.config_parsers import verify_search_service_available
from app.services.integrations import search_verify
from app.services.integrations.search_verify import (
    invalidate_search_verify_cache,
    verify_search_config_live,
)

_ANSWER = [SearchResult(title="Forbidden City", link="https://example.com/a", snippet="snippet")]
_RATE_LIMITED = RuntimeError("429 Too Many Requests")


@dataclass
class ProviderStub:
    """What every provider answers (keyed by API key) and which providers were actually called."""

    outcomes: dict[str, list[SearchResult] | Exception] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)


@pytest.fixture
def providers() -> Iterator[ProviderStub]:
    stub = ProviderStub()

    class _Client:
        def __init__(self, key: str) -> None:
            self._key = key

        async def search(self, query: str, num_results: int = 5, **kwargs: object) -> list[SearchResult]:
            stub.calls.append(self._key)
            outcome = stub.outcomes[self._key]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    async def build_client(self: WebSearcher, bypass_gateway: bool = False) -> _Client:
        return _Client(self.config.api_key or self.config.api_base or "")

    invalidate_search_verify_cache()
    reset_search_coalescing_state_for_tests()
    default_quota_tracker.reset_all()
    with patch.object(WebSearcher, "_get_search_service", build_client):
        yield stub
    invalidate_search_verify_cache()
    reset_search_coalescing_state_for_tests()
    default_quota_tracker.reset_all()


def _member(slug: str, key: str | None = None, *, api_base: str | None = None) -> SearchServiceConfig:
    return SearchServiceConfig(search_service=slug, api_key=key, api_base=api_base, search_max_retries=0)


def _chain(*members: SearchServiceConfig) -> SearchServiceConfig:
    """Shape of ``extract_active_search_config``: the head's fields plus the full ordered chain."""
    return members[0].model_copy(update={"provider_chain": list(members)})


# ── chain-aware verdict ───────────────────────────────────────────


async def test_blocked_head_with_healthy_backup_is_available(providers: ProviderStub) -> None:
    providers.outcomes = {"head-key": [], "backup-key": _ANSWER}
    cfg = _chain(_member("tavily", "head-key"), _member("brave", "backup-key"))

    assert await verify_search_service_available(cfg) is True
    assert providers.calls == ["head-key", "backup-key"]


async def test_failing_head_with_healthy_backup_is_available(providers: ProviderStub) -> None:
    providers.outcomes = {"head-key": _RATE_LIMITED, "backup-key": _ANSWER}
    cfg = _chain(_member("tavily", "head-key"), _member("brave", "backup-key"))

    assert await verify_search_service_available(cfg) is True
    assert providers.calls == ["head-key", "backup-key"]


async def test_healthy_head_never_contacts_backup(providers: ProviderStub) -> None:
    providers.outcomes = {"head-key": _ANSWER, "backup-key": _ANSWER}
    cfg = _chain(_member("tavily", "head-key"), _member("brave", "backup-key"))

    assert await verify_search_service_available(cfg) is True
    assert providers.calls == ["head-key"]


async def test_chain_where_every_member_answers_empty_is_unavailable(providers: ProviderStub) -> None:
    providers.outcomes = {"head-key": [], "backup-key": []}
    cfg = _chain(_member("tavily", "head-key"), _member("brave", "backup-key"))

    assert await verify_search_service_available(cfg) is False
    assert providers.calls == ["head-key", "backup-key"]


async def test_chain_where_every_member_fails_is_unavailable(providers: ProviderStub) -> None:
    providers.outcomes = {"head-key": _RATE_LIMITED, "backup-key": RuntimeError("503 upstream down")}
    cfg = _chain(_member("tavily", "head-key"), _member("brave", "backup-key"))

    assert await verify_search_service_available(cfg) is False


async def test_chain_without_any_credentials_is_unavailable_without_contacting_providers(
    providers: ProviderStub,
) -> None:
    cfg = _chain(_member("tavily"), _member("brave"))

    assert await verify_search_service_available(cfg) is False
    assert providers.calls == []


async def test_head_without_credentials_does_not_veto_a_configured_backup(providers: ProviderStub) -> None:
    providers.outcomes = {"": RuntimeError("missing credentials"), "backup-key": _ANSWER}
    cfg = _chain(_member("tavily"), _member("brave", "backup-key"))

    assert await verify_search_service_available(cfg) is True


async def test_e2e_probe_key_on_chain_head_skips_probe(providers: ProviderStub) -> None:
    cfg = _chain(_member("tavily", "test-tavily-key"), _member("brave", "backup-key"))

    assert await verify_search_service_available(cfg) is True
    assert providers.calls == []


async def test_verdict_cache_is_keyed_by_the_whole_chain(providers: ProviderStub) -> None:
    providers.outcomes = {"head-key": _RATE_LIMITED, "good-backup": _ANSWER, "bad-backup": _RATE_LIMITED}
    healthy_chain = _chain(_member("tavily", "head-key"), _member("brave", "good-backup"))
    broken_chain = _chain(_member("tavily", "head-key"), _member("serper", "bad-backup"))

    assert await verify_search_service_available(healthy_chain) is True
    assert await verify_search_service_available(broken_chain) is False


async def test_missing_config_is_unavailable() -> None:
    assert await verify_search_service_available(None) is False


# ── single provider ───────────────────────────────────────────────


async def test_single_provider_with_credentials_is_probed(providers: ProviderStub) -> None:
    providers.outcomes = {"key": _ANSWER}

    assert await verify_search_service_available(_member("tavily", "key")) is True
    assert providers.calls == ["key"]


@pytest.mark.parametrize(
    "cfg",
    [
        _member("tavily"),
        _member("searxng"),
        _member("not-a-provider", "key"),
    ],
    ids=["api-key-missing", "searxng-base-missing", "unknown-slug"],
)
async def test_single_provider_without_what_the_catalog_requires_is_unavailable(
    providers: ProviderStub, cfg: SearchServiceConfig
) -> None:
    assert await verify_search_config_live(cfg) is False
    assert providers.calls == []


async def test_searxng_needs_only_its_base_url(providers: ProviderStub) -> None:
    providers.outcomes = {"http://localhost:8081": _ANSWER}

    assert await verify_search_config_live(_member("searxng", api_base="http://localhost:8081")) is True


# ── verdict cache ─────────────────────────────────────────────────


async def test_verdict_is_reused_within_ttl(providers: ProviderStub) -> None:
    providers.outcomes = {"key": _RATE_LIMITED}
    cfg = _member("tavily", "key")

    assert await verify_search_service_available(cfg) is False
    assert await verify_search_service_available(cfg) is False
    assert providers.calls == ["key"]


async def test_verdict_is_probed_again_after_ttl(providers: ProviderStub, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_verify, "_VERIFY_TTL_SECONDS", 0.05)
    providers.outcomes = {"key": _RATE_LIMITED}
    cfg = _member("tavily", "key")

    await verify_search_service_available(cfg)
    await asyncio.sleep(0.1)
    await verify_search_service_available(cfg)

    assert providers.calls == ["key", "key"]


async def test_invalidation_forces_a_new_probe(providers: ProviderStub) -> None:
    providers.outcomes = {"key": _RATE_LIMITED}
    cfg = _member("tavily", "key")

    await verify_search_service_available(cfg)
    invalidate_search_verify_cache()
    await verify_search_service_available(cfg)

    assert providers.calls == ["key", "key"]
