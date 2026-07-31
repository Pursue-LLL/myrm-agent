from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.companion.pet_store import InstalledPet
from tests.services.companion.test_pet_store import _write_installed_pet
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
def companion_app():
    return build_minimal_app(preset="companion")


@pytest.fixture
def pet_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_companion_pet_install_and_serve_api(
    companion_app,
    pet_data_dir: Path,
) -> None:
    from myrm_agent_harness.core.features import init_features

    from app.services.features.registration import register_all_features

    register_all_features()
    init_features(overrides={"companion_mode": True})

    sprite_path = pet_data_dir / "companion" / "pets" / "nous-girl" / "spritesheet.webp"
    installed = InstalledPet(
        slug="nous-girl",
        display_name="Nous Girl",
        directory=sprite_path.parent,
        spritesheet=sprite_path,
        content_sha256="deadbeef" * 8,
    )

    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
        with (
            patch(
                "app.services.companion.pet_store.install_pet",
                new=AsyncMock(return_value=installed),
            ),
            patch(
                "app.api.companion.router._persist_sprite_selection",
                new=AsyncMock(),
            ) as persist_mock,
        ):
            resp = await ac.post("/api/v1/companion/pets/install", json={"slug": "nous-girl"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["slug"] == "nous-girl"
        assert payload["display_name"] == "Nous Girl"
        persist_mock.assert_awaited_once()

        _write_installed_pet(pet_data_dir, "nous-girl", sha=installed.content_sha256)

        serve_resp = await ac.get("/api/v1/companion/pets/nous-girl/spritesheet")
        assert serve_resp.status_code == 200
        assert serve_resp.headers["content-type"].startswith("image/")
        assert serve_resp.content == b"fake-webp-bytes"

        missing_resp = await ac.get("/api/v1/companion/pets/missing-pet/spritesheet")
        assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_companion_pet_uninstall_clears_matching_sprite_config(
    companion_app,
    pet_data_dir: Path,
) -> None:
    from myrm_agent_harness.core.features import init_features

    from app.services.features.registration import register_all_features

    register_all_features()
    init_features(overrides={"companion_mode": True})

    _write_installed_pet(pet_data_dir, "nous-girl", sha="deadbeef" * 8)
    _write_installed_pet(pet_data_dir, "lobster", sha="cafebabe" * 8)

    async with AsyncClient(transport=ASGITransport(app=companion_app), base_url="http://test") as ac:
        set_payload = {
            "value": {
                "name": "Ferris",
                "sprite": {
                    "pet_slug": "nous-girl",
                    "content_sha256": "deadbeef" * 8,
                    "display_name": "Nous Girl",
                },
            },
            "deviceId": "default_device",
        }
        set_resp = await ac.post("/api/v1/companion/config", json=set_payload)
        assert set_resp.status_code == 200

        delete_resp = await ac.delete("/api/v1/companion/pets/nous-girl")
        assert delete_resp.status_code == 200
        assert delete_resp.json()["removed"] is True

        config_resp = await ac.get("/api/v1/companion/config")
        assert config_resp.status_code == 200
        config_value = config_resp.json()["value"]
        assert config_value["name"] == "Ferris"
        assert config_value["sprite"] is None

        list_resp = await ac.get("/api/v1/companion/pets")
        slugs = [pet["slug"] for pet in list_resp.json()["pets"]]
        assert "nous-girl" not in slugs
        assert "lobster" in slugs

        # Uninstall non-active pet — sprite config for another slug must remain
        restore_payload = {
            "value": {
                "name": "Ferris",
                "sprite": {
                    "pet_slug": "nous-girl",
                    "content_sha256": "deadbeef" * 8,
                    "display_name": "Nous Girl",
                },
            },
            "deviceId": "default_device",
        }
        restore_resp = await ac.post("/api/v1/companion/config", json=restore_payload)
        assert restore_resp.status_code == 200

        delete_other = await ac.delete("/api/v1/companion/pets/lobster")
        assert delete_other.status_code == 200

        config_after = await ac.get("/api/v1/companion/config")
        sprite_after = config_after.json()["value"]["sprite"]
        assert sprite_after is not None
        assert sprite_after["pet_slug"] == "nous-girl"
        assert config_after.json()["value"]["name"] == "Ferris"
