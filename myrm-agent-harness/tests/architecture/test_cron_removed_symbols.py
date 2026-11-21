"""The cron toolkit does not name a symbol it no longer defines.

``_REMOVED`` lists names the toolkit does not define. One that appears in a module is dead code, and one that a doc row
still lists describes code that does not exist, so the scan covers the toolkit's modules and its ``_ARCH.md`` files. A
name that gets a real definition again leaves the list in the same change.

[INPUT]
- src/myrm_agent_harness/toolkits/cron/**/*.py and **/*.md: the files that must not name a removed symbol

[OUTPUT]
- that no cron module or module doc names a removed symbol, and that the scan sees one when it is there

[POS]
Zero-residue gate for the symbols removed from the cron toolkit. The scan is whole-word, so a longer name that merely
contains a removed one does not trip it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_CRON = Path(__file__).resolve().parents[2] / "src" / "myrm_agent_harness" / "toolkits" / "cron"

_REMOVED = (
    "parse_loop_command_input",  # parser of the `/loop` command text
    "parse_natural_interval",  # natural-language interval parser behind it
    "is_top_of_hour_cron",  # top-of-hour cron test; resolve_stagger_ms decides the stagger window
    "compute_stagger_offset_s",  # per-job stagger offset; resolve_stagger_ms decides the window
    "active_streams",  # StreamListener status accessor
    "claim_due",  # store write that cleared a job's next run time when its run was claimed; advance_next_run books instead
    "is_stale_run",  # test for a claimed job that never ran again; a booked job always has a next run time
    "list_orphaned_active",  # store query for enabled jobs without a next run time; none can arise
    "_recover_stale_runs",  # startup phase that revived claimed jobs
    "_active_jobs",  # set of dispatched job ids on the scheduler; the in-flight counter replaces it
    "_execute_and_persist",  # scheduler entry that ran a claimed job; _dispatch is the guarded run
    "execute_fn",  # StartupRecovery's run callback; admit_fn books and launches
    "generate_fix_suggestion",  # per-category troubleshooting text; a failed delivery is reported by category and message
    "ConnectorHealthStatus",  # health state of a destination; judging health from failures is the application's rule
    "_NON_OUTBOUND_CHANNELS",  # channels that stay inside the application; the application decides which those are
    "PROCESS_ERROR",  # failure category for a connector's child process; no delivery runs one
)


def residue(text: str, names: tuple[str, ...] = _REMOVED) -> list[str]:
    """The removed names that occur in ``text`` as whole words."""
    return [name for name in names if re.search(rf"\b{re.escape(name)}\b", text)]


def test_removed_symbols_stay_removed() -> None:
    files = sorted([*_CRON.rglob("*.py"), *_CRON.rglob("*.md")])
    assert files, f"the scan found no cron files under {_CRON}"
    found = {
        str(path.relative_to(_CRON)): names for path in files if (names := residue(path.read_text(encoding="utf-8")))
    }

    assert not found, found


def test_scan_sees_a_removed_name() -> None:
    assert residue("def active_streams(self) -> dict[str, str]: ...") == ["active_streams"]


def test_scan_ignores_a_longer_name() -> None:
    assert residue("inactive_streams_total = 0") == []
