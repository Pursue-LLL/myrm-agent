"""Tests for artifact share static bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.artifacts.share_bundle import (
    ShareBundleManifest,
    _pick_entry_name,
    _write_deploy_files,
    _write_manifest,
    bundle_dir_for_claims,
    purge_expired_share_bundles,
    resolve_share_bundle_file,
)
from app.services.artifacts.share_token import ArtifactShareClaims
from app.services.deploy.deploy_packager import DeployFile


def test_pick_entry_prefers_index_html() -> None:
    files = {
        "styles.css": DeployFile(path="styles.css", content="body{}", encoding="utf-8"),
        "index.html": DeployFile(path="index.html", content="<html/>", encoding="utf-8"),
    }
    assert _pick_entry_name(files) == "index.html"


def test_pick_entry_single_pdf() -> None:
    files = {"report.pdf": DeployFile(path="report.pdf", content="abc", encoding="base64")}
    assert _pick_entry_name(files) == "report.pdf"


def test_pick_entry_rejects_multiple_html_without_index() -> None:
    files = {
        "a.html": DeployFile(path="a.html", content="<html/>", encoding="utf-8"),
        "b.html": DeployFile(path="b.html", content="<html/>", encoding="utf-8"),
    }
    with pytest.raises(ValueError, match="index.html"):
        _pick_entry_name(files)


def test_resolve_share_bundle_file_blocks_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.artifacts.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="a1", version_id="v1", exp=9_999_999_999)
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(
        bundle_root,
        {
            "index.html": DeployFile(path="index.html", content="<html/>", encoding="utf-8"),
            "styles.css": DeployFile(path="styles.css", content="x{}", encoding="utf-8"),
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


def test_manifest_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.artifacts.share_bundle.settings.database.state_dir",
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
        "app.services.artifacts.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    claims = ArtifactShareClaims(artifact_id="exp", version_id="v1", exp=1)
    bundle_root = bundle_dir_for_claims(claims)
    bundle_root.mkdir(parents=True, exist_ok=True)
    _write_manifest(bundle_root, entry="index.html", exp=1)
    (bundle_root / "index.html").write_text("<html/>", encoding="utf-8")

    purge_expired_share_bundles()
    assert not bundle_root.exists()
