"""Materialize shareable artifact static bundles for public preview links.

[INPUT]
- app.services.deploy.artifact_files::resolve_artifact_deploy_files (POS: vault + asset_root packaging)
- app.services.deploy.deploy_packager::DeployFile, validate_deploy_payload
- app.services.artifacts.share_token::ArtifactShareClaims (POS: HMAC claims)
- app.config.settings::settings (POS: state_dir root)

[OUTPUT]
- materialize_share_bundle: write TTL bundle under state_dir
- resolve_share_bundle_file: safe path lookup for public GET

[POS]
Server business layer — mirrors deploy static packaging for read-only multi-file HTML shares.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.services.artifacts.share_token import ArtifactShareClaims
from app.services.deploy.artifact_files import resolve_artifact_deploy_files
from app.services.deploy.deploy_packager import DeployFile, validate_deploy_payload

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "manifest.json"
_BUNDLE_SUBDIR = "artifact-shares"


@dataclass(frozen=True)
class ShareBundleManifest:
    entry: str
    exp: int


def _bundles_root() -> Path:
    root = Path(settings.database.state_dir or ".") / _BUNDLE_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def bundle_dir_for_claims(claims: ArtifactShareClaims) -> Path:
    """Stable directory name from pinned artifact version and expiry."""
    digest = hashlib.sha256(f"{claims.artifact_id}:{claims.version_id}:{claims.exp}".encode("utf-8")).hexdigest()
    return _bundles_root() / digest


def _pick_entry_name(files: dict[str, DeployFile]) -> str:
    if "index.html" in files:
        return "index.html"
    if len(files) == 1:
        return next(iter(files))
    html_entries = [name for name in files if name.lower().endswith((".html", ".htm"))]
    if len(html_entries) == 1:
        return html_entries[0]
    raise ValueError("Share bundle must include index.html or a single HTML entry")


def _write_deploy_files(bundle_root: Path, files: dict[str, DeployFile]) -> None:
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)
    for entry_name, deploy_file in files.items():
        dest = bundle_root / entry_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if deploy_file.encoding == "utf-8":
            dest.write_text(deploy_file.content, encoding="utf-8")
        else:
            dest.write_bytes(base64.b64decode(deploy_file.content))


def _has_html_payload(files: dict[str, DeployFile]) -> bool:
    return any(name.lower().endswith((".html", ".htm")) for name in files)


def _load_manifest(bundle_root: Path) -> ShareBundleManifest | None:
    manifest_path = bundle_root / _MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    entry = raw.get("entry")
    exp = raw.get("exp")
    if not isinstance(entry, str) or not isinstance(exp, int):
        return None
    return ShareBundleManifest(entry=entry, exp=exp)


def _write_manifest(bundle_root: Path, *, entry: str, exp: int) -> None:
    manifest_path = bundle_root / _MANIFEST_NAME
    manifest_path.write_text(
        json.dumps({"entry": entry, "exp": exp}, separators=(",", ":")),
        encoding="utf-8",
    )


def purge_expired_share_bundles() -> None:
    """Remove bundle directories whose manifest expiry is in the past."""
    root = _bundles_root()
    now = int(time.time())
    for child in root.iterdir():
        if not child.is_dir():
            continue
        manifest = _load_manifest(child)
        if manifest is None or manifest.exp < now:
            shutil.rmtree(child, ignore_errors=True)


async def materialize_share_bundle(
    db: AsyncSession,
    workspace_root: str,
    claims: ArtifactShareClaims,
) -> ShareBundleManifest:
    """Collect deploy-equivalent files and persist them for public multi-file serving."""
    purge_expired_share_bundles()
    _artifact, files = await resolve_artifact_deploy_files(
        db, claims.artifact_id, workspace_root, version_id=claims.version_id
    )
    if not files:
        raise ValueError("No files to share")

    if _has_html_payload(files):
        validate_deploy_payload(files)

    entry = _pick_entry_name(files)
    bundle_root = bundle_dir_for_claims(claims)
    _write_deploy_files(bundle_root, files)
    _write_manifest(bundle_root, entry=entry, exp=claims.exp)
    logger.info(
        "Materialized artifact share bundle: artifact=%s version=%s files=%d",
        claims.artifact_id,
        claims.version_id,
        len(files),
    )
    return ShareBundleManifest(entry=entry, exp=claims.exp)


def _guess_media_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".md", ".markdown")):
        return "text/markdown; charset=utf-8"
    if lower.endswith(".txt"):
        return "text/plain; charset=utf-8"
    return "text/html; charset=utf-8"


def bundle_asset_count(claims: ArtifactShareClaims) -> int:
    """Count non-manifest files in a materialized bundle."""
    bundle_root = bundle_dir_for_claims(claims)
    if not bundle_root.is_dir():
        return 0
    return sum(1 for path in bundle_root.rglob("*") if path.is_file() and path.name != _MANIFEST_NAME)


def resolve_share_bundle_file(
    claims: ArtifactShareClaims,
    relative_path: str | None,
) -> tuple[Path, str, str] | None:
    """Return (disk_path, media_type, filename) when the bundle contains the requested asset."""
    bundle_root = bundle_dir_for_claims(claims)
    manifest = _load_manifest(bundle_root)
    if manifest is None or manifest.exp < int(time.time()):
        return None

    rel = (relative_path or manifest.entry).lstrip("/")
    if not rel:
        rel = manifest.entry

    target = (bundle_root / rel).resolve()
    root_resolved = bundle_root.resolve()
    if not str(target).startswith(str(root_resolved)):
        return None
    if not target.is_file() or target.name == _MANIFEST_NAME:
        return None

    filename = target.name
    return target, _guess_media_type(filename), filename
