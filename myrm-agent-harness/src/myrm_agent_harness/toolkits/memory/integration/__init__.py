"""Integration Memory — external service data memorisation for cross-source semantic retrieval.

[OUTPUT]
- IntegrationProvider: Protocol for data fetching from external services.
- IntegrationLeaf, IntegrationNodeKind, IntegrationTree, IntegrationSyncOutcome, IntegrationSyncResult: data models of fetched records, the summary tree and sync runs
- fetcher::IntegrationFetcher, tree_manager::IntegrationTreeManager, summarizer::IntegrationSummariser: fetch scheduler, summary tree manager and LLM summariser (imported from their modules, not re-exported here)

[POS]
Integration Memory sub-module.  Pulls data from third-party services (Gmail,
GitHub, Slack, Notion, …) into the local memory system, enabling cross-source
semantic retrieval without live API calls. Exposed to product via REST API /
GUI in `myrm-agent-server.app.api.integrations`; Agent reads results through
the general memory toolkit (no dedicated Agent tools).
"""

from myrm_agent_harness.toolkits.memory.integration.protocols import IntegrationProvider
from myrm_agent_harness.toolkits.memory.integration.types import (
    IntegrationLeaf,
    IntegrationNodeKind,
    IntegrationSyncOutcome,
    IntegrationSyncResult,
    IntegrationTree,
)

__all__ = [
    "IntegrationLeaf",
    "IntegrationNodeKind",
    "IntegrationProvider",
    "IntegrationSyncOutcome",
    "IntegrationSyncResult",
    "IntegrationTree",
]
