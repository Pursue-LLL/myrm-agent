"""Model resolution must never write provider credentials to the logs."""

from __future__ import annotations

import logging

import pytest

from app.services.agent.params.models import ModelSelection
from app.services.agent.params.resolvers import _resolve_model_config

_SECRET = "custom-key-not-matching-any-redaction-prefix"


async def test_resolving_a_model_does_not_log_provider_api_keys(caplog: pytest.LogCaptureFixture) -> None:
    providers_dict: dict[str, object] = {
        "providers": [
            {
                "id": "openai",
                "isEnabled": True,
                "providerType": "openai",
                "apiKeys": [{"isActive": True, "key": _SECRET}],
            }
        ]
    }

    with caplog.at_level(logging.DEBUG, logger="app.services.agent.params.resolvers"):
        cfg = await _resolve_model_config(ModelSelection(provider_id="openai", model="gpt-4o"), providers_dict)

    assert cfg.api_key == _SECRET
    assert "Resolving model config for openai" in caplog.text
    assert _SECRET not in caplog.text
