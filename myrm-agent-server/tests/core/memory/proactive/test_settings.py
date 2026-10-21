"""Tests for proactive follow-up settings resolution."""

from __future__ import annotations

import pytest

from app.core.memory.proactive.settings import resolve_memory_enabled


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (None, False),
        ({}, False),
        ({"enableMemory": False}, False),
        ({"enableMemory": True}, True),
        ({"enableMemory": "true"}, False),
    ],
)
def test_resolve_memory_enabled(settings: dict[str, object] | None, expected: bool) -> None:
    assert resolve_memory_enabled(settings) is expected
