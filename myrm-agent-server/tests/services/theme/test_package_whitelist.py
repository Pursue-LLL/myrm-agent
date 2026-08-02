"""Tests for theme package whitelist helpers."""

from app.services.theme.package.whitelist import (
    is_allowed_package_entry,
    is_animated_image,
    is_animated_webp,
    is_unsafe_entry_path,
    is_valid_mp4,
)


def test_allows_recipe_and_hero() -> None:
    assert is_allowed_package_entry('recipe.json')
    assert is_allowed_package_entry('hero.png')
    assert is_allowed_package_entry('poster.jpg')
    assert is_allowed_package_entry('preview.webp')
    assert is_allowed_package_entry('motion.mp4')


def test_rejects_nested_and_traversal_paths() -> None:
    assert is_unsafe_entry_path('../hero.png')
    assert is_unsafe_entry_path('nested/hero.png')
    assert not is_allowed_package_entry('nested/hero.png')
    assert not is_allowed_package_entry('payload.exe')


def test_valid_mp4_magic() -> None:
    assert is_valid_mp4(b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00')
    assert not is_valid_mp4(b'not-a-video')


def test_rejects_animated_webp() -> None:
    webp = b'RIFF' + b'\x00' * 4 + b'WEBP' + b'VP8X' + b'\x00' * 4 + bytes([0x02])
    assert is_animated_webp(webp)
    assert is_animated_image('hero.webp', webp)
