"""The Hardware Cookbook reads its model specs from the bundled asset, not from a mock.

[POS]
tests/api/integrations/hardware/test_model_specs.py

[INPUT]
- app.api.integrations.hardware.model_specs: the bundled-spec loader behind the cookbook recommendations

[OUTPUT]
- Pins that the loader finds assets/cookbook_specs.json from where the module lives; every hardware API test patches
  `get_dynamic_model_specs`, so a loader that looks in the wrong directory would pass them all and fail in production
"""

from __future__ import annotations

import asyncio

import pytest

from app.api.integrations.hardware import model_specs


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_specs, "_CACHE", None)


def test_the_bundled_specs_path_is_the_shipped_asset() -> None:
    path = model_specs._bundled_specs_path()
    assert path.is_file(), f"{path} is not the bundled cookbook spec asset"
    assert path.name == "cookbook_specs.json"
    assert path.parent.name == "assets"


def test_the_loader_returns_the_shipped_specs() -> None:
    specs = asyncio.run(model_specs.get_dynamic_model_specs())
    assert specs, "the cookbook needs at least one model spec"
    assert all(isinstance(spec, dict) for spec in specs)
