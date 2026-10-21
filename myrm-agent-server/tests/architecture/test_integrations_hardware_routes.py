"""Ensure integrations hardware routes are mounted at the public API paths."""

from __future__ import annotations

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


def test_integrations_hardware_routes_registered() -> None:
    paths = set(app.openapi().get("paths", {}))
    expected = {
        "/api/v1/integrations/hardware/recommendations",
        "/api/v1/integrations/hardware/ollama/pull",
        "/api/v1/integrations/hardware/ollama/models",
    }
    missing = sorted(path for path in expected if path not in paths)
    assert not missing, f"Missing integrations hardware routes: {missing}"
