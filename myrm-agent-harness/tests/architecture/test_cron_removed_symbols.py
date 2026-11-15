"""The cron toolkit does not name a symbol it has removed.

Each name in ``_REMOVED`` was deleted because nothing in production called it. A merge or a pasted snippet that brings
one back is dead code again, and a doc row that still lists one describes code that is gone, so the scan covers the
toolkit's modules and its ``_ARCH.md`` files. A name that is later reused for something real is taken off the list here,
with the reason.

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
    "parse_loop_command_input",  # parser of the `/loop` command text; only its own tests called it
    "parse_natural_interval",  # its only production caller was parse_loop_command_input
    "is_top_of_hour_cron",  # only compute_stagger_offset_s called it; resolve_stagger_ms decides the stagger window
    "compute_stagger_offset_s",  # no production caller
    "active_streams",  # StreamListener status accessor that nothing read
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
