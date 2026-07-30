"""Wiki external source sync — deterministic pull into raw/ (zero LLM).

[OUTPUT]
- run_wiki_source_sync: orchestrates Gmail/RSS pulls → publish_raw → optional compile enqueue
"""

from app.services.wiki.source_sync.runner import run_wiki_source_sync
from app.services.wiki.source_sync.schemas import (
    WikiSourceSyncConfig,
    WikiSourceSyncResult,
    WikiSourceSyncRunSummary,
)

__all__ = [
    "WikiSourceSyncConfig",
    "WikiSourceSyncResult",
    "WikiSourceSyncRunSummary",
    "run_wiki_source_sync",
]
