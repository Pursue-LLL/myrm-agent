"""Unit tests for server harness import architecture helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.test_server_harness_imports import (
    _collect_harness_imports,
    _load_baseline,
)


@pytest.mark.architecture
def test_collect_harness_imports_includes_api_facades() -> None:
    imports = _collect_harness_imports()
    assert "myrm_agent_harness.api.hooks" in imports
    assert "myrm_agent_harness.api.skills" in imports
    assert "myrm_agent_harness.api" in imports


@pytest.mark.architecture
def test_collect_harness_imports_excludes_private_modules() -> None:
    imports = _collect_harness_imports()
    private = [path for path in imports if "._" in path]
    assert private == []


@pytest.mark.architecture
def test_baseline_matches_current_imports() -> None:
    baseline = _load_baseline()
    current = _collect_harness_imports()
    assert baseline == current


@pytest.mark.architecture
def test_baseline_file_is_sorted_unique() -> None:
    baseline_path = Path(__file__).resolve().parent / "data" / "server_harness_import_baseline.txt"
    lines = [line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines == sorted(set(lines))
