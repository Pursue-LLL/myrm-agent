"""Tests for artifact share static bundles."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.services.artifacts.share.share_bundle import (
    ShareBundleManifest,
    _pick_entry_name,
    _write_deploy_files,
    _write_manifest,
    bundle_dir_for_claims,
    purge_expired_share_bundles,
    resolve_share_bundle_file,
)
from app.services.artifacts.share.share_token import ArtifactShareClaims
from app.services.hosting.packager import PublishFile


def test_pick_entry_prefers_index_html() -> None:
    files = {
        "styles.css": PublishFile(path="styles.css", content="body{}", encoding="utf-8"),
        "index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8"),
    }
    assert _pick_entry_name(files) == "index.html"


def test_pick_entry_single_pdf() -> None:
    files = {"report.pdf": PublishFile(path="report.pdf", content="abc", encoding="base64")}
    assert _pick_entry_name(files) == "report.pdf"


def test_pick_entry_rejects_multiple_html_without_index() -> None:
    files = {
        "a.html": PublishFile(path="a.html", content="<html/>", encoding="utf-8"),
        "b.html": PublishFile(path="b.html", content="<html/>", encoding="utf-8"),
    }
    with pytest.raises(ValueError, match="index.html"):
        _pick_entry_name(files)


def test_pick_entry_single_non_index_html() -> None:
    """A lone HTML entry that is not named index.html is still the entry."""
    files = {
        "report.html": PublishFile(path="report.html", content="<html/>", encoding="utf-8"),
        "report.css": PublishFile(path="report.css", content="x{}", encoding="utf-8"),
    }
    assert _pick_entry_name(files) == "report.html"


def test_write_deploy_files_overwrites_existing_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-materializing a bundle replaces stale on-disk files."""
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="ow1", version_id="v1", exp=9_999_999_999)
    bundle_root = bundle_dir_for_claims(claims)
    first = {"index.html": PublishFile(path="index.html", content="old", encoding="utf-8")}
    _write_deploy_files(bundle_root, first)
    assert (bundle_root / "index.html").read_text(encoding="utf-8") == "old"
    (bundle_root / "stale.txt").write_text("junk", encoding="utf-8")

    second = {"index.html": PublishFile(path="index.html", content="new", encoding="utf-8")}
    _write_deploy_files(bundle_root, second)
    assert (bundle_root / "index.html").read_text(encoding="utf-8") == "new"
    assert not (bundle_root / "stale.txt").exists()


def test_load_manifest_tolerates_corrupt_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="corrupt", version_id="v1", exp=9_999_999_999)
    bundle_root = bundle_dir_for_claims(claims)
    bundle_root.mkdir(parents=True, exist_ok=True)
    (bundle_root / "manifest.json").write_text("{not json", encoding="utf-8")
    assert resolve_share_bundle_file(claims, None) is None

    (bundle_root / "manifest.json").write_text('{"entry": 42, "exp": "bad"}', encoding="utf-8")
    assert resolve_share_bundle_file(claims, None) is None


def test_purge_skips_non_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-directory entries under the bundle root are ignored by purge."""
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    root = bundle_dir_for_claims(ArtifactShareClaims(artifact_id="skip", version_id="v1", exp=9_999_999_999))
    root.parent.mkdir(parents=True, exist_ok=True)
    (root.parent / ".DS_Store").write_text("junk", encoding="utf-8")
    purge_expired_share_bundles()
    assert (root.parent / ".DS_Store").exists()


def test_guess_media_type_fallbacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown-extension assets fall back to explicit content types."""
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    monkeypatch.setattr("mimetypes.guess_type", lambda filename: (None, None))
    claims = ArtifactShareClaims(artifact_id="media", version_id="v1", exp=9_999_999_999)
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(
        bundle_root,
        {
            "index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8"),
            "notes.md": PublishFile(path="notes.md", content="hi", encoding="utf-8"),
            "notes.txt": PublishFile(path="notes.txt", content="hi", encoding="utf-8"),
            "report.pdf": PublishFile(path="report.pdf", content="YWJj", encoding="base64"),
        },
    )
    _write_manifest(bundle_root, entry="index.html", exp=claims.exp)

    assert resolve_share_bundle_file(claims, "notes.md")[1] == "text/markdown; charset=utf-8"
    assert resolve_share_bundle_file(claims, "notes.txt")[1] == "text/plain; charset=utf-8"
    assert resolve_share_bundle_file(claims, "report.pdf")[1] == "application/pdf"


def test_resolve_extensionless_entry_uses_artifact_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Extension-less bundle entries resolve media type from token artifact_type."""
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    monkeypatch.setattr("mimetypes.guess_type", lambda filename: (None, None))
    claims = ArtifactShareClaims(artifact_id="doc", version_id="v1", exp=9_999_999_999, artifact_type="document")
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(
        bundle_root,
        {
            "季度报告": PublishFile(path="季度报告", content="# Title", encoding="utf-8"),
        },
    )
    _write_manifest(bundle_root, entry="季度报告", exp=claims.exp)

    resolved = resolve_share_bundle_file(claims, None)
    assert resolved is not None
    assert resolved[1] == "text/markdown; charset=utf-8"

    html_claims = ArtifactShareClaims(artifact_id="doc", version_id="v1", exp=9_999_999_999, artifact_type="html")
    resolved_html = resolve_share_bundle_file(html_claims, None)
    assert resolved_html is not None
    assert resolved_html[1] == "text/html; charset=utf-8"


def test_resolve_empty_relative_falls_back_to_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty relative path is normalized to the manifest entry."""
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="empty", version_id="v1", exp=9_999_999_999)
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(
        bundle_root,
        {"index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8")},
    )
    _write_manifest(bundle_root, entry="/", exp=claims.exp)
    assert resolve_share_bundle_file(claims, None) is None


def test_resolve_share_bundle_file_blocks_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="a1", version_id="v1", exp=9_999_999_999)
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(
        bundle_root,
        {
            "index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8"),
            "styles.css": PublishFile(path="styles.css", content="x{}", encoding="utf-8"),
        },
    )
    _write_manifest(bundle_root, entry="index.html", exp=claims.exp)

    entry = resolve_share_bundle_file(claims, None)
    assert entry is not None
    assert entry[2] == "index.html"

    css = resolve_share_bundle_file(claims, "styles.css")
    assert css is not None

    escaped = resolve_share_bundle_file(claims, "../outside.txt")
    assert escaped is None


def test_resolve_share_bundle_file_blocks_prefix_sibling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sibling dir whose name is a string-prefix of the digest must not be reachable.

    The containment check is path-relative (is_relative_to), so prefix-matching
    directory names cannot escape the bundle boundary.
    """
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(
        artifact_id="a1",
        version_id="v1",
        exp=int(time.time()) + 3600,
    )
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(
        bundle_root,
        {"index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8")},
    )
    _write_manifest(bundle_root, entry="index.html", exp=claims.exp)

    sibling = bundle_root.parent / f"{bundle_root.name}_evil"
    sibling.mkdir(parents=True, exist_ok=True)
    (sibling / "secret.txt").write_text("LEAKED", encoding="utf-8")

    escaped = resolve_share_bundle_file(claims, f"../{bundle_root.name}_evil/secret.txt")
    assert escaped is None


def test_resolve_share_bundle_file_allows_nested_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nested assets inside the bundle must still resolve after the strict containment check."""
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(
        artifact_id="a1",
        version_id="v1",
        exp=int(time.time()) + 3600,
    )
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(
        bundle_root,
        {"index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8")},
    )
    _write_manifest(bundle_root, entry="index.html", exp=claims.exp)
    (bundle_root / "assets").mkdir(parents=True, exist_ok=True)
    (bundle_root / "assets" / "style.css").write_text("body{}", encoding="utf-8")

    resolved = resolve_share_bundle_file(claims, "assets/style.css")
    assert resolved is not None
    assert resolved[0].name == "style.css"
    assert resolved[1] == "text/css"


def test_manifest_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="a2", version_id="v2", exp=9_999_999_999)
    bundle_root = bundle_dir_for_claims(claims)
    bundle_root.mkdir(parents=True, exist_ok=True)
    _write_manifest(bundle_root, entry="index.html", exp=claims.exp)
    raw = json.loads((bundle_root / "manifest.json").read_text(encoding="utf-8"))
    manifest = ShareBundleManifest(entry=raw["entry"], exp=raw["exp"])
    assert manifest.entry == "index.html"
    assert manifest.exp == claims.exp


def test_purge_expired_share_bundles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="exp", version_id="v1", exp=1)
    bundle_root = bundle_dir_for_claims(claims)
    bundle_root.mkdir(parents=True, exist_ok=True)
    _write_manifest(bundle_root, entry="index.html", exp=1)
    (bundle_root / "index.html").write_text("<html/>", encoding="utf-8")

    purge_expired_share_bundles()
    assert not bundle_root.exists()
