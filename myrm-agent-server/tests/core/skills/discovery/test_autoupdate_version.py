"""Autoupdate version SSOT helpers."""

from __future__ import annotations

from app.core.skills.discovery.autoupdate import _resolve_installed_version


def test_resolve_installed_version_prefers_catalog() -> None:
    assert _resolve_installed_version("2.1.0", {}) == "2.1.0"


def test_resolve_installed_version_falls_back_to_origin() -> None:
    assert _resolve_installed_version("1.0.0", {"version": "3.0.1"}) == "3.0.1"
