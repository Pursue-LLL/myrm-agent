"""Shared fixtures for real-LLM e2e integration tests of the content-extraction layer.

Loads credentials from ``myrm-agent/myrm-agent-server/.env.test`` (the same
file pytest uses for server-side integration/e2e suites) and builds real
``TransportChatModel`` instances for the BASIC (agnes hub) and LITE (minimax) model
lanes. Tests that require a real model must opt in via ``@pytest.mark.e2e``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_ENV_TEST = Path(__file__).resolve().parents[4] / "myrm-agent-server" / ".env.test"

from tests.integration.llm_extraction.llm_creds import route_config_for


@pytest.fixture(autouse=True)
def _load_env_test() -> None:
    """Load .env.test into the process environment (never overriding existing vars)."""
    if not _ENV_TEST.exists():
        pytest.skip(f"{_ENV_TEST} not found — real-LLM e2e cannot run")
    for line in _ENV_TEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if key and value:
            os.environ.setdefault(key, value)


def build_llm_for(key_prefix: str):
    """Build a real TransportChatModel from ``<PREFIX>_API_KEY/BASE_URL/MODEL`` env vars."""
    api_key, base_url, route_model_id, provider = route_config_for(key_prefix)
    from myrm_agent_harness.toolkits.llms.adapters.chat_model import TransportChatModel

    # A reasoning model's thinking counts toward max_tokens; a budget sized for the answer alone cuts a long think off
    # with the answer still unwritten (a JSON array ends mid-way and parses to nothing).
    return TransportChatModel(
        model=route_model_id,
        api_key=api_key,
        api_base=base_url,
        custom_llm_provider=provider,
        temperature=0.0,
        max_tokens=16384,
    )


@pytest.fixture
def basic_llm():
    """Real LLM on the BASIC lane (agnes hub by default)."""
    return build_llm_for("BASIC")


@pytest.fixture
def lite_llm():
    """Real LLM on the LITE lane (minimax by default)."""
    return build_llm_for("LITE")
