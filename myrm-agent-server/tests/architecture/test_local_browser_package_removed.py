"""Architecture gate: local_browser server package must not exist."""

from __future__ import annotations

from pathlib import Path


def test_local_browser_service_package_removed() -> None:
    services_root = Path(__file__).resolve().parents[2] / "app" / "services"
    assert not (services_root / "local_browser").exists()
