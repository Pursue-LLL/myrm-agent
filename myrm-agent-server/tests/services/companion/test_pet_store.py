from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.companion.pet_store import (
    InstalledPet,
    PetStoreError,
    install_pet,
    list_installed_pets,
    load_pet,
    uninstall_pet,
)


@pytest.fixture
def pet_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))
    return tmp_path


def _write_installed_pet(root: Path, slug: str, *, sha: str = "abc123") -> Path:
    directory = root / "companion" / "pets" / slug
    directory.mkdir(parents=True, exist_ok=True)
    sprite_path = directory / "spritesheet.webp"
    sprite_path.write_bytes(b"fake-webp-bytes")
    meta = {
        "id": slug,
        "displayName": f"Pet {slug}",
        "spritesheetPath": sprite_path.name,
        "contentSha256": sha,
    }
    (directory / "pet.json").write_text(json.dumps(meta), encoding="utf-8")
    return directory


def test_load_pet_returns_none_when_missing(pet_data_dir: Path) -> None:
    assert load_pet("missing-pet") is None


def test_list_installed_pets_reads_disk(pet_data_dir: Path) -> None:
    _write_installed_pet(pet_data_dir, "nous-girl", sha="deadbeef")
    pets = list_installed_pets()
    assert len(pets) == 1
    assert pets[0].slug == "nous-girl"
    assert pets[0].display_name == "Pet nous-girl"
    assert pets[0].content_sha256 == "deadbeef"


def test_uninstall_pet_removes_directory(pet_data_dir: Path) -> None:
    directory = _write_installed_pet(pet_data_dir, "to-remove")
    assert directory.is_dir()
    assert uninstall_pet("to-remove") is True
    assert not directory.exists()
    assert uninstall_pet("to-remove") is False


@pytest.mark.asyncio
async def test_install_pet_downloads_and_persists(pet_data_dir: Path) -> None:
    from PIL import Image

    manifest_entry = {
        "slug": "nous-girl",
        "displayName": "Nous Girl",
        "spritesheetUrl": "https://petdex.dev/pets/nous-girl/spritesheet.webp",
    }

    async def fake_download(_url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
        image.save(dest, format="WEBP")

    with (
        patch(
            "app.services.companion.pet_store._find_manifest_entry",
            new=AsyncMock(return_value=manifest_entry),
        ),
        patch("app.services.companion.pet_store._download_url", side_effect=fake_download),
    ):
        installed = await install_pet("nous-girl")

    assert isinstance(installed, InstalledPet)
    assert installed.slug == "nous-girl"
    assert installed.display_name == "Nous Girl"
    assert installed.spritesheet.is_file()
    assert len(installed.content_sha256) == 64

    reloaded = load_pet("nous-girl")
    assert reloaded is not None
    assert reloaded.content_sha256 == installed.content_sha256


@pytest.mark.asyncio
async def test_install_pet_is_idempotent_without_force(pet_data_dir: Path) -> None:
    _write_installed_pet(pet_data_dir, "cached-pet", sha="cached-sha")

    with patch(
        "app.services.companion.pet_store._find_manifest_entry",
        new=AsyncMock(side_effect=AssertionError("manifest should not be fetched")),
    ):
        installed = await install_pet("cached-pet")

    assert installed.slug == "cached-pet"
    assert installed.content_sha256 == "cached-sha"


@pytest.mark.asyncio
async def test_install_pet_rejects_invalid_atlas(pet_data_dir: Path) -> None:
    from PIL import Image

    manifest_entry = {
        "slug": "bad-pet",
        "displayName": "Bad Pet",
        "spritesheetUrl": "https://petdex.dev/pets/bad-pet/spritesheet.webp",
    }

    async def fake_download(_url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        image.save(dest, format="WEBP")

    with (
        patch(
            "app.services.companion.pet_store._find_manifest_entry",
            new=AsyncMock(return_value=manifest_entry),
        ),
        patch("app.services.companion.pet_store._download_url", side_effect=fake_download),
    ):
        with pytest.raises(PetStoreError, match="Spritesheet|Invalid|grid"):
            await install_pet("bad-pet")

    assert load_pet("bad-pet") is None


@pytest.mark.asyncio
async def test_install_pet_rejects_invalid_slug() -> None:
    with pytest.raises(PetStoreError, match="invalid pet slug"):
        await install_pet(".")
