"""Unit tests for cron trusted desktop app key resolution."""

from __future__ import annotations

from app.core.cron.adapters.agent_runner import resolve_trusted_desktop_keys


def test_names_resolve_to_keys():
    assert resolve_trusted_desktop_keys(({"name": "SAP GUI"},)) == ("sap gui",)


def test_app_id_preferred():
    assert resolve_trusted_desktop_keys(
        ({"name": "SAP", "app_id": "com.sap.gui"},)
    ) == ("com.sap.gui",)


def test_unresolvable_entries_skipped():
    assert resolve_trusted_desktop_keys(({"name": ""}, {"name": "  "})) == ()


def test_empty_is_empty():
    assert resolve_trusted_desktop_keys(()) == ()
