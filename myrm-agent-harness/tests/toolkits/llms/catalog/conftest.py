"""Fixtures shared by the catalog tests."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.catalog import store


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registrations a test makes never outlive it."""
    monkeypatch.setattr(store, "_REGISTERED", {})
