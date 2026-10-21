"""Unit tests for trusted desktop app entry normalization."""

from __future__ import annotations

from app.services.agent.profile.profile_resolver import (
    _normalize_trusted_desktop_apps as normalize,
)


def test_plain_names():
    assert normalize(["SAP GUI"]) == ({"name": "SAP GUI"},)


def test_dict_with_app_id():
    assert normalize([{"display_name": "SAP", "app_id": "com.sap.gui"}]) == (
        {"name": "SAP", "app_id": "com.sap.gui"},
    )


def test_invalid_entries_dropped():
    assert normalize([{"name": ""}, {"name": "  "}, 42, None]) == ()


def test_non_list_rejected():
    assert normalize("SAP GUI") == ()
    assert normalize(None) == ()
