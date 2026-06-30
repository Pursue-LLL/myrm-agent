"""Tests for hosting provider registry."""

from __future__ import annotations

import pytest

from app.services.hosting.registry import get_hosting_provider


def test_get_hosting_provider_vercel() -> None:
    provider = get_hosting_provider("vercel")
    assert provider.provider_type == "vercel"


def test_get_hosting_provider_unsupported() -> None:
    with pytest.raises(ValueError, match="Unsupported hosting provider"):
        get_hosting_provider("unknown")


@pytest.mark.parametrize(
    ("provider_type", "expected"),
    [
        ("vercel", "vercel"),
        ("cloudflare_pages", "cloudflare_pages"),
        ("netlify", "netlify"),
        ("http_webhook", "http_webhook"),
    ],
)
def test_get_hosting_provider_all_types(provider_type: str, expected: str) -> None:
    assert get_hosting_provider(provider_type).provider_type == expected
