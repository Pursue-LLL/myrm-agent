"""Tests for Google Workspace write scope detection in oauth_store."""

from __future__ import annotations

from app.services.integrations.oauth_store import (
    google_drive_read_enabled,
    google_workspace_write_enabled,
)


def test_write_enabled_requires_both_scopes() -> None:
    scope = (
        "openid email profile "
        "https://www.googleapis.com/auth/calendar.readonly "
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/drive.readonly "
        "https://www.googleapis.com/auth/gmail.send "
        "https://www.googleapis.com/auth/calendar.events"
    )
    assert google_workspace_write_enabled(scope) is True


def test_write_disabled_when_readonly_only() -> None:
    scope = (
        "openid https://www.googleapis.com/auth/calendar.readonly "
        "https://www.googleapis.com/auth/gmail.readonly"
    )
    assert google_workspace_write_enabled(scope) is False


def test_write_disabled_for_invalid_scope() -> None:
    assert google_workspace_write_enabled(None) is False
    assert google_workspace_write_enabled("") is False


def test_drive_read_enabled_when_scope_present() -> None:
    scope = (
        "openid email profile "
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/drive.readonly"
    )
    assert google_drive_read_enabled(scope) is True


def test_drive_read_disabled_when_scope_missing() -> None:
    scope = "openid https://www.googleapis.com/auth/gmail.readonly"
    assert google_drive_read_enabled(scope) is False
    assert google_drive_read_enabled(None) is False
