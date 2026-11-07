"""Synthetic package and server trees for the module-reachability engine tests.

[INPUT]
- scripts.module_reachability_engine::Report (POS: analysis result whose dead units a test compares; typing only)

[OUTPUT]
- HUB: relative path of the ``agent/engine`` hub that every synthetic package carries
- package: write package ``pkg`` (hub in place) plus the given files and return its root
- server_tree: write a consumer tree ``server`` holding exactly the given files and return its root
- dead: the keys of the units a report found dead

[POS]
Pytest-only helper shared by the module-reachability engine tests, so each test states the files it is
about and not how a tree is laid out on disk. Every tree lives under ``tmp_path``: the tests are hermetic
and neither import the harness nor read its tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.module_reachability_engine import Report

HUB = "agent/engine/__init__.py"


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def package(tmp_path: Path, files: dict[str, str]) -> Path:
    """Package ``pkg`` with the hub in place; ``files`` may replace the hub."""
    return _write_tree(tmp_path / "pkg", {"__init__.py": "", "agent/__init__.py": "", HUB: "", **files})


def server_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    """Consumer tree ``server`` holding exactly ``files``."""
    return _write_tree(tmp_path / "server", files)


def dead(report: Report) -> set[str]:
    return {unit.key for unit in report.dead}
