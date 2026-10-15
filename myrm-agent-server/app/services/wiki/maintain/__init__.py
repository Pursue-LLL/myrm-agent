"""Wiki maintain domain — orchestration, schemas, and state persistence.

[INPUT]
- app.services.wiki.maintain.runner (POS: maintain pipeline SSOT)
- app.services.wiki.maintain.run_registry (POS: single flight + live state of the maintain run per vault scope)
- app.services.wiki.maintain.schemas (POS: maintain DTOs)
- app.services.wiki.maintain.state_store (POS: wikiMaintainState persistence)

[OUTPUT]
- run_wiki_maintain_job: blocking maintain run (cron) + state persistence
- schedule_wiki_maintain / WikiMaintainScheduleResult / get_wiki_maintain_run: background run for the REST API and its live state
- WikiMaintainState / WikiMaintainRunResult / WikiMaintainModeLiteral

[POS]
Domain subpackage for wiki maintain. Facade module name ``app.services.wiki.maintain``
aggregates runner / schemas / state_store.
"""

from __future__ import annotations

from app.services.wiki.maintain.run_registry import get_wiki_maintain_run
from app.services.wiki.maintain.runner import (
    WikiMaintainScheduleResult,
    run_wiki_maintain_job,
    schedule_wiki_maintain,
)
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
    "WikiMaintainScheduleResult",
    "WikiMaintainState",
    "get_wiki_maintain_run",
    "load_wiki_maintain_state",
    "run_wiki_maintain_job",
    "save_wiki_maintain_state",
    "schedule_wiki_maintain",
    "state_from_run_result",
]
