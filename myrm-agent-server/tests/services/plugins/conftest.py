"""Fixtures for expert-export tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.support.export_world import ExportWorld


@pytest.fixture
def world() -> Iterator[ExportWorld]:
    with ExportWorld().installed() as installation:
        yield installation
