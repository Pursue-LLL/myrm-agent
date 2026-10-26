"""Fixtures of the CLI runtime tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ._fakes import FakeCli


@pytest.fixture
def fake_cli(tmp_path: Path) -> FakeCli:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    return FakeCli(bin_dir)
