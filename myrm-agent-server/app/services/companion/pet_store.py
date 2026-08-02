"""On-disk Petdex pet install store for Companion sprite overlays.

[INPUT]
- MYRM_DATA_DIR companion pets directory (POS: local pet install root)
- pet.json manifest + spritesheet assets (POS: installed pet payload)

[OUTPUT]
- PetStore: list/install/remove installed pets for WebUI Companion

[POS]
Server persistence for GUI Petdex installs; mirrors Hermes pet store boundaries without CLI coupling.

Pets live under ``{MYRM_DATA_DIR}/companion/pets/<slug>/`` with ``pet.json`` and
a local spritesheet copy. Mirrors Hermes ``agent/pet/store.py`` boundaries
(profile-scoped disk, petdex host pinning) without CLI/npm coupling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app.services.companion.pet_atlas import AtlasReport

import httpx

logger = logging.getLogger(__name__)

PETDEX_MANIFEST_URL = "https://petdex.dev/api/manifest"
_DOWNLOAD_TIMEOUT = 60.0
_MAX_SPRITESHEET_BYTES = 5 * 1024 * 1024
_MANIFEST_CACHE_TTL_SECONDS = 300.0

_manifest_cache: dict[str, Any] | None = None
_manifest_cached_at: float = 0.0


class PetStoreError(RuntimeError):
    """Raised on install, IO, or validation failures."""


@dataclass(frozen=True, slots=True)
class InstalledPet:
    slug: str
    display_name: str
    directory: Path
    spritesheet: Path
    content_sha256: str
    format_label: str | None = None
    format_tier: str | None = None

    @property
    def exists(self) -> bool:
        return self.spritesheet.is_file()


def resolve_data_dir() -> Path:
    raw = os.environ.get("MYRM_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".myrm"


def pets_dir() -> Path:
    path = resolve_data_dir() / "companion" / "pets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_slug(slug: str) -> str:
    segment = Path(str(slug).strip()).name
    if segment in ("", ".", ".."):
        return ""
    return segment


def _is_petdex_host(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "petdex.dev" or host.endswith(".petdex.dev")


def _read_pet_json(directory: Path) -> dict[str, Any]:
    pet_json = directory / "pet.json"
    if not pet_json.is_file():
        return {}
    try:
        loaded = json.loads(pet_json.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError) as exc:
        logger.debug("Unreadable pet.json in %s: %s", directory, exc)
        return {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _fetch_manifest() -> list[dict[str, Any]]:
    global _manifest_cache, _manifest_cached_at
    now = time.monotonic()
    if _manifest_cache is not None and now - _manifest_cached_at < _MANIFEST_CACHE_TTL_SECONDS:
        pets = _manifest_cache.get("pets")
        return pets if isinstance(pets, list) else []

    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(PETDEX_MANIFEST_URL)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise PetStoreError("Invalid petdex manifest payload")
    pets_raw = payload.get("pets")
    if not isinstance(pets_raw, list):
        raise PetStoreError("Invalid petdex manifest pets list")

    entries: list[dict[str, Any]] = [entry for entry in pets_raw if isinstance(entry, dict)]
    _manifest_cache = {"pets": entries}
    _manifest_cached_at = now
    return entries


async def _find_manifest_entry(slug: str) -> dict[str, Any]:
    normalized = _safe_slug(slug)
    if not normalized:
        raise PetStoreError("invalid pet slug")
    for entry in await _fetch_manifest():
        entry_slug = entry.get("slug")
        if isinstance(entry_slug, str) and entry_slug == normalized:
            return entry
    raise PetStoreError(f"pet '{normalized}' is not in the petdex manifest")


async def _download_url(url: str, dest: Path) -> None:
    if not _is_petdex_host(url):
        raise PetStoreError(f"refusing non-petdex download host: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            total = 0
            with dest.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_SPRITESHEET_BYTES:
                        raise PetStoreError(
                            f"spritesheet exceeds {_MAX_SPRITESHEET_BYTES} byte limit"
                        )
                    handle.write(chunk)


def _atlas_fields_from_meta(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    atlas_raw = meta.get("atlasReport")
    if not isinstance(atlas_raw, dict):
        return None, None
    label = atlas_raw.get("label")
    tier = atlas_raw.get("formatTier") or atlas_raw.get("format_tier")
    return (
        str(label) if isinstance(label, str) and label.strip() else None,
        str(tier) if isinstance(tier, str) and tier.strip() else None,
    )


def persist_atlas_report(slug: str, report: AtlasReport) -> None:
    """Write a fresh atlas report into pet.json for the given installed pet."""
    from app.services.companion.pet_atlas import atlas_report_dict

    normalized = _safe_slug(slug)
    if not normalized:
        return
    pet = load_pet(normalized)
    if pet is None:
        return
    pet_json = pet.directory / "pet.json"
    meta: dict[str, Any] = {}
    if pet_json.is_file():
        try:
            loaded = json.loads(pet_json.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, ValueError) as exc:
            logger.warning("Could not read pet.json for atlas persist (%s): %s", normalized, exc)
    meta["atlasReport"] = atlas_report_dict(report)
    try:
        pet_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not persist atlas report for %s: %s", normalized, exc)


def load_pet(slug: str) -> InstalledPet | None:
    normalized = _safe_slug(slug)
    if not normalized:
        return None
    directory = pets_dir() / normalized
    if not directory.is_dir():
        return None
    meta = _read_pet_json(directory)
    spritesheet_name = str(meta.get("spritesheetPath", "") or "").strip()
    if spritesheet_name:
        spritesheet = directory / spritesheet_name
    else:
        webp = directory / "spritesheet.webp"
        png = directory / "spritesheet.png"
        spritesheet = webp if webp.is_file() else png
    if not spritesheet.is_file():
        return None
    sha = str(meta.get("contentSha256", "") or "")
    if not sha:
        sha = _sha256_file(spritesheet)
    display_name = str(meta.get("displayName", "") or normalized)
    format_label, format_tier = _atlas_fields_from_meta(meta)
    return InstalledPet(
        slug=normalized,
        display_name=display_name,
        directory=directory,
        spritesheet=spritesheet,
        content_sha256=sha,
        format_label=format_label,
        format_tier=format_tier,
    )


def list_installed_pets() -> list[InstalledPet]:
    root = pets_dir()
    installed: list[InstalledPet] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        pet = load_pet(child.name)
        if pet is not None and pet.exists:
            installed.append(pet)
    return installed


async def install_pet(slug: str, *, force: bool = False) -> InstalledPet:
    normalized = _safe_slug(slug)
    if not normalized:
        raise PetStoreError("invalid pet slug")

    existing = load_pet(normalized)
    if existing is not None and existing.exists and not force:
        return existing

    entry = await _find_manifest_entry(normalized)
    spritesheet_url = entry.get("spritesheetUrl")
    if not isinstance(spritesheet_url, str) or not spritesheet_url.strip():
        raise PetStoreError(f"manifest entry for '{normalized}' has no spritesheetUrl")
    if not _is_petdex_host(spritesheet_url):
        raise PetStoreError(f"refusing non-petdex spritesheet host for '{normalized}'")

    directory = pets_dir() / normalized
    directory.mkdir(parents=True, exist_ok=True)

    lowered = spritesheet_url.lower().split("?", maxsplit=1)[0]
    ext = ".png" if lowered.endswith(".png") else ".webp"
    sprite_path = directory / f"spritesheet{ext}"

    await _download_url(spritesheet_url, sprite_path)

    from app.services.companion.pet_atlas import FormatTier, analyze_spritesheet, atlas_report_dict

    try:
        atlas_report = analyze_spritesheet(sprite_path)
    except ValueError as exc:
        sprite_path.unlink(missing_ok=True)
        raise PetStoreError(f"spritesheet validation failed: {exc}") from exc

    if atlas_report.format_tier == FormatTier.FAIL:
        sprite_path.unlink(missing_ok=True)
        raise PetStoreError(atlas_report.message)

    content_sha256 = _sha256_file(sprite_path)

    display_name = str(entry.get("displayName", "") or normalized)
    meta: dict[str, Any] = {
        "id": normalized,
        "displayName": display_name,
        "spritesheetPath": sprite_path.name,
        "contentSha256": content_sha256,
        "sourceUrl": spritesheet_url,
        "installedAt": int(time.time()),
        "atlasReport": atlas_report_dict(atlas_report),
    }
    (directory / "pet.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    installed = InstalledPet(
        slug=normalized,
        display_name=display_name,
        directory=directory,
        spritesheet=sprite_path,
        content_sha256=content_sha256,
        format_label=atlas_report.label,
        format_tier=atlas_report.format_tier.value,
    )
    logger.info("Installed companion pet slug=%s sha=%s", normalized, content_sha256[:12])
    return installed


def uninstall_pet(slug: str) -> bool:
    normalized = _safe_slug(slug)
    if not normalized:
        return False
    directory = pets_dir() / normalized
    if not directory.is_dir():
        return False
    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink(missing_ok=True)
    directory.rmdir()
    return True


def spritesheet_media_type(path: Path) -> str:
    if path.suffix.lower() == ".png":
        return "image/png"
    return "image/webp"


__all__ = [
    "InstalledPet",
    "PetStoreError",
    "install_pet",
    "list_installed_pets",
    "load_pet",
    "pets_dir",
    "resolve_data_dir",
    "spritesheet_media_type",
    "uninstall_pet",
]
