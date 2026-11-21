"""The policy of a served artifact share page: which sources load, and what stays closed."""

from __future__ import annotations

import re

from app.core.security.share.share_csp import ARTIFACT_SHARE_CSP, SHARE_CDN_SOURCES


def _directives(policy: str) -> dict[str, list[str]]:
    return {name: sources for name, *sources in (part.split() for part in policy.split(";") if part.strip())}


def test_scripts_styles_and_fonts_load_from_the_own_origin_and_the_cdn_list() -> None:
    directives = _directives(ARTIFACT_SHARE_CSP)

    for name in ("script-src", "style-src", "font-src"):
        assert "'self'" in directives[name], name
        assert set(SHARE_CDN_SOURCES) <= set(directives[name]), name


def test_images_stay_own_origin_and_connections_stay_closed() -> None:
    directives = _directives(ARTIFACT_SHARE_CSP)

    assert directives["default-src"] == ["'none'"]
    assert directives["img-src"] == ["'self'", "data:", "blob:"]
    assert directives["media-src"] == ["'self'", "data:", "blob:"]
    assert directives["connect-src"] == ["'none'"]
    assert directives["frame-src"] == ["'none'"]
    assert directives["object-src"] == ["'none'"]


def test_every_cdn_is_one_https_origin() -> None:
    """No wildcard, bare scheme or path: each entry names exactly one host."""
    for source in SHARE_CDN_SOURCES:
        assert re.fullmatch(r"https://[a-z0-9.-]+", source), source
    assert len(set(SHARE_CDN_SOURCES)) == len(SHARE_CDN_SOURCES)
