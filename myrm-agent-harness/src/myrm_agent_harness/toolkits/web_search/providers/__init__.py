"""Search provider adapters and orchestration.

[INPUT]
- providers.chain::search_provider_chain (POS: Executes N-provider priority chain with wall-clock budget, per-hop allowance for hung providers, hand-over on empty answers, and self-healing quota auto-skip; cooldowns are scoped per credential, never per provider slug)
- providers.rest_search::RestSearch (POS: REST client for the keyed search providers, loaded on first access)
- providers.web_searcher::WebSearcher, SearchServiceConfig, SearchServiceType (POS: Web search orchestrator)

[OUTPUT]
- Re-exports: WebSearcher, SearchServiceConfig, SearchServiceType, RestSearch, search_provider_chain

[POS]
Subpackage entry for search provider adapters and orchestration.
"""

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.web_search.providers.chain import search_provider_chain
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
    SearchServiceConfig,
    SearchServiceType,
    WebSearcher,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_search.providers.rest_search import RestSearch

__all__ = [
    "RestSearch",
    "SearchServiceConfig",
    "SearchServiceType",
    "WebSearcher",
    "search_provider_chain",
]


def __getattr__(name: str) -> object:
    """Load RestSearch on first access so importing the providers stays light."""
    if name == "RestSearch":
        from myrm_agent_harness.toolkits.web_search.providers.rest_search import RestSearch

        globals()[name] = RestSearch
        return RestSearch
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
