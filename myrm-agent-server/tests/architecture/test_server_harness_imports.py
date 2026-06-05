"""Architecture test: prevent new deep imports of harness internals from server."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_BASELINE_PATH = Path(__file__).resolve().parent / "data" / "server_harness_import_baseline.txt"
_APP_ROOT = _SERVER_ROOT / "app"


def _collect_harness_imports() -> frozenset[str]:
    imports: set[str] = set()
    for path in _APP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            match = re.match(r"^\s*(?:from|import)\s+(myrm_agent_harness[^\s#]+)", line)
            if match:
                imports.add(match.group(1).split(" import")[0].strip())
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("myrm_agent_harness"):
                        imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("myrm_agent_harness"):
                imports.add(node.module)
    return frozenset(imports)


def _load_baseline() -> frozenset[str]:
    lines = _BASELINE_PATH.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip() for line in lines if line.strip())


@pytest.mark.architecture
def test_no_new_server_deep_harness_imports() -> None:
    """Open-source server must not grow new direct harness internal import paths."""
    baseline = _load_baseline()
    current = _collect_harness_imports()
    new_imports = sorted(current - baseline)
    assert not new_imports, (
        "New deep harness imports detected in myrm-agent-server. "
        "Use myrm_agent_harness.api or update baseline only if intentional:\n" + "\n".join(new_imports)
    )
