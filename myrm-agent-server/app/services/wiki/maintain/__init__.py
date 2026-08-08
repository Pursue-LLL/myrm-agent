"""Wiki maintain domain — orchestration, schemas, and state persistence.

[INPUT]
- app.services.wiki.maintain.runner (POS: maintain pipeline SSOT)
- app.services.wiki.maintain.schemas (POS: maintain DTOs)
- app.services.wiki.maintain.state_store (POS: wikiMaintainState persistence)

[OUTPUT]
- run_wiki_maintain_job: deterministic maintain pipeline + state persistence
- WikiMaintainState / WikiMaintainRunResult / WikiMaintainModeLiteral

[POS]
Domain subpackage for wiki maintain. Facade module name ``app.services.wiki.maintain``
aggregates runner / schemas / state_store.
"""

from __future__ import annotations

from app.services.wiki.maintain.runner import run_wiki_maintain_job
from app.services.wiki.maintain.schemas import (
    WikiMaintainModeLiteral,
    WikiMaintainRunResult,
    WikiMaintainState,
)
from app.services.wiki.maintain.state_store import (
    load_wiki_maintain_state,
    save_wiki_maintain_state,
    state_from_run_result,
)

__all__ = [
    "WikiMaintainModeLiteral",
    "WikiMaintainRunResult",
    "WikiMaintainState",
    "load_wiki_maintain_state",
    "run_wiki_maintain_job",
    "save_wiki_maintain_state",
    "state_from_run_result",
]
