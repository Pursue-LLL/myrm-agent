"""Ensure the integrations Ollama route is mounted at the public API path."""

from __future__ import annotations

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


def test_integrations_ollama_chat_model_route_registered() -> None:
    paths = set(app.openapi().get("paths", {}))
    assert "/api/v1/integrations/ollama/chat-model" in paths
