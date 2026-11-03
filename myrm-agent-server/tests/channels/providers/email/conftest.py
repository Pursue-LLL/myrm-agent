"""Fixtures shared by the email channel tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _save_into_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Attachments are saved as temp files; keep them in the test's own directory so none outlives the run."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
