"""The pets routes sit behind the companion feature gate, and a legacy sprite selection is migrated or dropped."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.core.features import init_features

from app.services.companion.pet_store import InstalledPet, PetStoreError
from app.services.config.service import config_service
from app.services.features.registration import register_all_features
from tests.support.minimal_app import build_minimal_app

_LEGACY_SPRITE = {"sheet_url": "https://example.test/sheet.webp", "name": "nous-girl"}


@pytest.fixture
def companion_app() -> FastAPI:
    return build_minimal_app(preset="companion")


def _enable_companion(enabled: bool) -> None:
    register_all_features()
    init_features(overrides={"companion_mode": enabled})


@pytest.mark.asyncio
async def test_pet_routes_are_closed_while_the_companion_feature_is_off(companion_app: FastAPI) -> None:
    _enable_companion(False)
    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
        listing = await ac.get("/api/v1/companion/pets")
        install = await ac.post("/api/v1/companion/pets/install", json={"slug": "nous-girl"})
        uninstall = await ac.delete("/api/v1/companion/pets/nous-girl")
        sheet = await ac.get("/api/v1/companion/pets/nous-girl/spritesheet")

    assert [r.status_code for r in (listing, install, uninstall, sheet)] == [403, 403, 403, 403]


@pytest.mark.asyncio
async def test_a_legacy_sprite_is_replaced_by_the_installed_pet(companion_app: FastAPI, tmp_path: Path) -> None:
    _enable_companion(True)
    await config_service.set(
        config_key="companion_config",
        value={"name": "Ferris", "sprite": _LEGACY_SPRITE},
        device_id="default_device",
    )
    installed = InstalledPet(
        slug="nous-girl",
        display_name="Nous Girl",
        directory=tmp_path,
        spritesheet=tmp_path / "spritesheet.webp",
        content_sha256="deadbeef" * 8,
    )

    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
        with patch("app.services.companion.pet_store.install_pet", new=AsyncMock(return_value=installed)):
            body = (await ac.get("/api/v1/companion/config")).json()
        stored = (await ac.get("/api/v1/companion/config")).json()

    assert body["value"]["name"] == "Ferris"
    assert body["value"]["sprite"] == {
        "pet_slug": "nous-girl",
        "content_sha256": "deadbeef" * 8,
        "display_name": "Nous Girl",
    }
    assert stored["value"]["sprite"]["pet_slug"] == "nous-girl"
    assert stored["version"] == body["version"]


@pytest.mark.asyncio
async def test_a_legacy_sprite_that_cannot_be_installed_is_dropped_and_the_rest_kept(companion_app: FastAPI) -> None:
    _enable_companion(True)
    await config_service.set(
        config_key="companion_config",
        value={"name": "Ferris", "hat": "Cowboy Hat", "sprite": _LEGACY_SPRITE},
        device_id="default_device",
    )

    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
        with patch("app.services.companion.pet_store.install_pet", new=AsyncMock(side_effect=PetStoreError("offline"))):
            body = (await ac.get("/api/v1/companion/config")).json()

    assert body["value"]["sprite"] is None
    assert (body["value"]["name"], body["value"]["hat"]) == ("Ferris", "Cowboy Hat")
