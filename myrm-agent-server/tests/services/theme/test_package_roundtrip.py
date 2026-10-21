"""Roundtrip and export tests for theme packages."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.storage.service import FilesService
from app.schemas.theme_profile import ThemeArtConfigModel, ThemePaletteTokensModel, ThemeProfileRecipeModel
from app.services.theme.package.export_service import export_theme_package
from app.services.theme.package.inspect_service import inspect_theme_package
from app.services.theme.package.install_service import install_theme_package


def _build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _sample_recipe(*, media_kind: str = "image", with_metadata: bool = False) -> dict[str, object]:
    art: dict[str, object] = {
        "focusX": 0.5,
        "focusY": 0.42,
        "wash": 0.4,
        "mediaKind": media_kind,
        "assetRef": "hero.png" if media_kind == "image" else "motion.mp4",
    }
    if media_kind == "video":
        art["posterAssetRef"] = "poster.jpg"
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "minEngineVersion": "1.0.0",
        "name": "Roundtrip Theme",
        "profile": {
            "name": "Roundtrip Theme",
            "layoutId": "full-bleed",
            "fontId": "inter",
            "palette": {
                "primaryLight": "#588e95",
                "primaryDark": "#6ba3aa",
                "primaryHoverLight": "#4a7d84",
                "primaryHoverDark": "#7eb5bc",
                "primaryDarkLight": "#10505a",
                "primaryDarkDark": "#588e95",
                "dualAccent": True,
            },
            "art": art,
        },
    }
    if with_metadata:
        payload["description"] = "Rainy workspace atmosphere"
        payload["tagline"] = "Calm focus"
        payload["author"] = "Myrm Studio"
        payload["previewFile"] = "preview.png"
    return payload


@pytest.fixture
def files_service() -> FilesService:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = LocalStorageBackend(base_path=tmpdir)
        yield FilesService(storage=storage)


def test_video_inspect_uses_poster_thumbnail() -> None:
    mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
    jpg = b"\xff\xd8\xff" + b"\x00" * 64
    recipe = json.dumps(_sample_recipe(media_kind="video")).encode("utf-8")
    zip_bytes = _build_zip({"recipe.json": recipe, "motion.mp4": mp4, "poster.jpg": jpg})
    result = inspect_theme_package(zip_bytes)
    assert result.can_import is True
    assert result.hero_thumbnail_base64 is not None
    assert result.hero_thumbnail_base64.startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_export_import_roundtrip(files_service: FilesService) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    preview = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64
    recipe = json.dumps(_sample_recipe(with_metadata=True)).encode("utf-8")
    original_zip = _build_zip(
        {
            "recipe.json": recipe,
            "hero.png": png,
            "preview.png": preview,
        },
    )

    inspect_first = inspect_theme_package(original_zip)
    assert inspect_first.can_import is True

    with patch("app.services.theme.package.install_service.files_service", files_service):
        profile, _ = await install_theme_package(
            inspect_first.session_id,
            set_active=True,
            existing_profile_ids=set(),
        )

    assert profile.art.assetRef is not None
    assert profile.art.assetRef.startswith("file:")
    assert profile.packageDescription == "Rainy workspace atmosphere"
    assert profile.packageTagline == "Calm focus"
    assert profile.packageAuthor == "Myrm Studio"

    with patch("app.services.theme.package.export_service.files_service", files_service):
        exported_zip = await export_theme_package(profile)

    inspect_second = inspect_theme_package(exported_zip)
    assert inspect_second.can_import is True
    assert inspect_second.name == "Roundtrip Theme"
    assert inspect_second.description == "Rainy workspace atmosphere"
    assert inspect_second.tagline == "Calm focus"
    assert inspect_second.author == "Myrm Studio"
    assert inspect_second.hero_thumbnail_base64 is not None


@pytest.mark.asyncio
async def test_export_from_profile_model(files_service: FilesService) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    uploaded = await files_service.upload_file("hero.png", png, "image/png")
    profile = ThemeProfileRecipeModel(
        id="preset/test",
        name="Export Test",
        layoutId="full-bleed",
        fontId="inter",
        palette=ThemePaletteTokensModel(
            primaryLight="#588e95",
            primaryDark="#6ba3aa",
            primaryHoverLight="#4a7d84",
            primaryHoverDark="#7eb5bc",
            primaryDarkLight="#10505a",
            primaryDarkDark="#588e95",
            dualAccent=True,
        ),
        art=ThemeArtConfigModel(
            focusX=0.5,
            focusY=0.5,
            wash=0.4,
            mediaKind="image",
            assetRef=f"file:{uploaded.id}",
        ),
    )

    with patch("app.services.theme.package.export_service.files_service", files_service):
        zip_bytes = await export_theme_package(profile)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = set(archive.namelist())
        assert "recipe.json" in names
        assert any(name.endswith(".png") for name in names)
        manifest = json.loads(archive.read("recipe.json"))
        assert manifest["schemaVersion"] == 1
        assert manifest["profile"]["art"]["assetRef"] is not None
