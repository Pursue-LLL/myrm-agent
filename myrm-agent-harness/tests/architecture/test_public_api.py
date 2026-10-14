"""Architecture tests for the public API boundary."""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.mark.architecture
def test_public_api_exports_are_importable() -> None:
    """All symbols in api.__all__ must resolve without error."""
    api = importlib.import_module("myrm_agent_harness.api")
    for name in api.__all__:
        assert hasattr(api, name), f"Missing public API export: {name}"


@pytest.mark.architecture
def test_public_api_factory_reexport() -> None:
    """create_skill_agent must be callable via the public API."""
    from myrm_agent_harness.api import create_skill_agent

    assert callable(create_skill_agent)


@pytest.mark.architecture
def test_api_package_has_no_heavy_side_effects_on_import() -> None:
    """Importing api.types must not pull in the agent factory."""
    import sys

    before = set(sys.modules)
    importlib.import_module("myrm_agent_harness.api.types")
    after = set(sys.modules)
    loaded = after - before
    assert "myrm_agent_harness.agent.skill_agent.factory" not in loaded
