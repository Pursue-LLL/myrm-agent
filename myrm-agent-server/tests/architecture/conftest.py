"""Membership of `tests/architecture/` in the architecture gate.

[INPUT]
- scripts/ci/run_architecture_gates.sh: selects tests by the `architecture` marker and rejects unregistered markers
- .github/workflows/desktop-contracts.yml, public-tree-guards.yml: run the files named below by path

[OUTPUT]
- the `architecture` marker, registered here and added to every test under this directory except the files named below

[POS]
The directory decides what the gate runs, so a test cannot be left out by forgetting to mark it; files another workflow
runs by path stay with that workflow. The gate rejects unregistered markers, so a misspelled marker or a lost
registration is a collection error instead of tests dropping out unnoticed.
"""

from __future__ import annotations

import pytest

# desktop-contracts.yml runs test_desktop_*.py and public-tree-guards.yml runs the other two files, the latter without
# any conftest. The trailing dots keep a name from matching a longer file name.
_RUN_BY_OTHER_WORKFLOWS = ("test_desktop_", "test_no_credential_literals.", "test_no_private_references.")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "architecture: runs in the architecture gate")


def pytest_itemcollected(item: pytest.Item) -> None:
    if not item.path.name.startswith(_RUN_BY_OTHER_WORKFLOWS):
        item.add_marker(pytest.mark.architecture)
