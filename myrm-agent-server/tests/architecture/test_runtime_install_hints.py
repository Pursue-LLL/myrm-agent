"""Runtime install hints must use uv sync, not pip install."""

from __future__ import annotations

from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"


@pytest.mark.architecture
def test_app_runtime_messages_avoid_pip_install() -> None:
    """User-facing app code must not suggest pip install."""
    offenders: list[str] = []
    for path in _APP_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "pip install" in text:
            offenders.append(str(path.relative_to(_APP_ROOT.parent)))
    assert offenders == [], f"pip install still present: {offenders}"


@pytest.mark.architecture
def test_registry_matrix_install_hint() -> None:
    from app.channels.providers.registry import _all_specs, _channel_install_hint

    specs = _all_specs()
    assert "uv sync --extra matrix" in _channel_install_hint("matrix", specs["matrix"])
    assert "channels-sdk" in _channel_install_hint("feishu", specs["feishu"])
    assert "channels-sdk" in _channel_install_hint("discord", specs["discord"])
