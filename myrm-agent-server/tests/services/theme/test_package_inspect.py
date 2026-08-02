"""Tests for theme package inspect service."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.services.theme.package.inspect_service import ThemePackageInspectError, inspect_theme_package


def _build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _sample_recipe(*, with_poster: bool = True, media_kind: str = 'image') -> dict[str, object]:
    art: dict[str, object] = {
        'focusX': 0.5,
        'focusY': 0.42,
        'wash': 0.4,
        'mediaKind': media_kind,
        'assetRef': 'hero.png' if media_kind == 'image' else 'motion.mp4',
    }
    if with_poster and media_kind == 'video':
        art['posterAssetRef'] = 'poster.jpg'
    return {
        'schemaVersion': 1,
        'minEngineVersion': '1.0.0',
        'name': 'Test Theme',
        'profile': {
            'name': 'Test Theme',
            'layoutId': 'full-bleed',
            'fontId': 'inter',
            'palette': {
                'primaryLight': '#588e95',
                'primaryDark': '#6ba3aa',
                'primaryHoverLight': '#4a7d84',
                'primaryHoverDark': '#7eb5bc',
                'primaryDarkLight': '#10505a',
                'primaryDarkDark': '#588e95',
                'dualAccent': True,
            },
            'art': art,
        },
    }


def test_inspect_image_package_success() -> None:
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
    recipe = json.dumps(_sample_recipe()).encode('utf-8')
    zip_bytes = _build_zip({'recipe.json': recipe, 'hero.png': png})
    result = inspect_theme_package(zip_bytes)
    assert result.can_import is True
    assert result.name == 'Test Theme'
    assert result.hero_thumbnail_base64 is not None


def test_inspect_rejects_video_without_poster() -> None:
    mp4 = b'\x00\x00\x00\x18ftypisom' + b'\x00' * 32
    recipe = json.dumps(_sample_recipe(with_poster=False, media_kind='video')).encode('utf-8')
    zip_bytes = _build_zip({'recipe.json': recipe, 'motion.mp4': mp4})
    result = inspect_theme_package(zip_bytes)
    assert result.can_import is False
    assert any('poster' in warning.lower() for warning in result.warnings)


def test_inspect_rejects_disallowed_file() -> None:
    recipe = json.dumps(_sample_recipe()).encode('utf-8')
    zip_bytes = _build_zip({'recipe.json': recipe, 'hero.png': b'png', 'evil.exe': b' MZ'})
    with pytest.raises(ThemePackageInspectError):
        inspect_theme_package(zip_bytes)


def test_inspect_rejects_animated_webp() -> None:
    webp = b'RIFF' + b'\x00' * 4 + b'WEBP' + b'VP8X' + b'\x00' * 4 + bytes([0x02]) + b'\x00' * 32
    recipe = json.dumps(_sample_recipe()).encode('utf-8')
    zip_bytes = _build_zip({'recipe.json': recipe, 'hero.webp': webp})
    with pytest.raises(ThemePackageInspectError):
        inspect_theme_package(zip_bytes)
