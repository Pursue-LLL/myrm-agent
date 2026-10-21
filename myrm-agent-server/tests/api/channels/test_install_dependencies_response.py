"""Tests for channel install-dependencies API response shape."""

from __future__ import annotations

from app.api.channels.schemas import ChannelInstallDependenciesResponse


def test_install_response_defaults_registered_true() -> None:
    payload = ChannelInstallDependenciesResponse(ok=True, message="done")
    assert payload.registered is True


def test_install_response_exposes_registered_false() -> None:
    payload = ChannelInstallDependenciesResponse(
        ok=True,
        message="pip ok; register failed",
        registered=False,
    )
    assert payload.registered is False
