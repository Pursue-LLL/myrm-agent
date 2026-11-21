"""The cron server code does not name a symbol it no longer defines.

``_REMOVED`` lists names the cron server code does not define. One that appears in a module is dead state, and one that
a doc row still lists describes code that does not exist, so the scan covers the cron modules, routes and services and
their ``_ARCH.md`` files. A name that gets a real definition again leaves the list in the same change.

[INPUT]
- app/core/cron, app/api/cron and app/services/cron (every *.py and *.md): the files that must not name a removed symbol

[OUTPUT]
- that no cron module, route, service or module doc names a removed symbol, and that the scan sees one when it is there

[POS]
Zero-residue gate for the symbols removed from the cron server code. The scan is whole-word, so a longer name that
merely contains a removed one does not trip it.
"""

from __future__ import annotations

import re
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[2]
_ROOTS = (
    _SERVER / "app" / "core" / "cron",
    _SERVER / "app" / "api" / "cron",
    _SERVER / "app" / "services" / "cron",
)

_REMOVED = (
    "active_streams",  # StreamListenerManager status accessor
    "active_polls",  # PollListenerManager status accessor
    "claim_due",  # store write that cleared a job's next run time when its run was claimed; advance_next_run books instead
    "list_orphaned_active",  # store query for enabled jobs without a next run time; none can arise
    "ConnectorHealthService",  # report over every destination; DeliveryHealthService answers for one destination
    "ConnectorHealthSummary",  # one row of that report
    "get_all_connectors_health",  # the call that built that report
    "connector_health_service",  # the module of that service
    "ConnectorHealthResponse",  # one row of the list response
    "ConnectorsHealthListResponse",  # the list response
    "connector_health_router",  # the list route; GET /{job_id}/delivery-health took its place
    "connectors/health",  # the path of that list route
)


def residue(text: str, names: tuple[str, ...] = _REMOVED) -> list[str]:
    """The removed names that occur in ``text`` as whole words."""
    return [name for name in names if re.search(rf"\b{re.escape(name)}\b", text)]


def test_removed_symbols_stay_removed() -> None:
    files = sorted(path for root in _ROOTS for pattern in ("*.py", "*.md") for path in root.rglob(pattern))
    assert files, f"the scan found no cron files under {_ROOTS}"
    found = {str(path.relative_to(_SERVER)): names for path in files if (names := residue(path.read_text(encoding="utf-8")))}

    assert not found, found


def test_scan_sees_a_removed_name() -> None:
    assert residue("def active_polls(self) -> dict[str, str]: ...") == ["active_polls"]


def test_scan_ignores_a_longer_name() -> None:
    assert residue("inactive_polls_total = 0") == []
