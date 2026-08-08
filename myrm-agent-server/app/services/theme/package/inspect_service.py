"""Inspect .myrmtheme ZIP packages (safe extract + manifest validation).

[INPUT]
myrm_agent_harness.backends.skills.scanning.archive_security (POS: ZIP 安全扫描)
myrm_agent_harness.backends.skills.scanning.zip_extract (POS: 安全解压)
app.services.theme.package.constants (POS: 包格式常量)
app.services.theme.package.manifest (POS: recipe.json schema)
app.services.theme.package.whitelist (POS: 条目白名单)

[OUTPUT]
inspect_theme_package(data) -> ThemePackageInspectResult

[POS]
安全解压 ZIP、校验白名单文件名、尺寸上限、animated 图片检测、
提取 recipe.json 解析为 Manifest + 缩略图 data URI；不触碰存储层。
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from dataclasses import dataclass

from myrm_agent_harness.backends.skills.scanning.archive_security import (
    ArchiveSecurityError,
    format_archive_security_user_message,
)
from myrm_agent_harness.backends.skills.scanning.zip_extract import safe_extract_zip
from pydantic import ValidationError

from app.services.theme.package.constants import (
    MAX_IMAGE_BYTES,
    MAX_MOTION_BYTES,
    MAX_PACKAGE_BYTES,
    MAX_PACKAGE_FILES,
    MAX_UNPACKED_BYTES,
    RECIPE_JSON,
)
from app.services.theme.package.manifest import ThemePackageManifestModel
from app.services.theme.package.session_store import create_session
from app.services.theme.package.whitelist import (
    is_allowed_package_entry,
    is_animated_image,
    is_image_entry,
    is_motion_entry,
    is_unsafe_entry_path,
    is_valid_mp4,
)


@dataclass(frozen=True, slots=True)
class ThemePackageInspectResult:
    session_id: str
    package_sha256: str
    can_import: bool
    warnings: list[str]
    signature_status: str
    name: str
    description: str | None
    tagline: str | None
    author: str | None
    layout_id: str
    font_id: str
    media_kind: str
    wash: float
    primary_light: str
    dual_accent: bool
    hero_mime: str | None
    hero_thumbnail_base64: str | None
    preview_thumbnail_base64: str | None


class ThemePackageInspectError(ValueError):
    """User-facing inspect failure."""


def inspect_theme_package(zip_bytes: bytes) -> ThemePackageInspectResult:
    if not zip_bytes:
        raise ThemePackageInspectError('Empty theme package')
    if len(zip_bytes) > MAX_PACKAGE_BYTES:
        raise ThemePackageInspectError('Theme package exceeds 24MB limit')

    package_sha256 = hashlib.sha256(zip_bytes).hexdigest()

    try:
        extracted = safe_extract_zip(
            zip_bytes,
            max_total_bytes=MAX_UNPACKED_BYTES,
            max_entries=MAX_PACKAGE_FILES,
            strip_top_dir=False,
        )
    except ArchiveSecurityError as error:
        raise ThemePackageInspectError(format_archive_security_user_message(error.violation)) from error
    except ValueError as error:
        raise ThemePackageInspectError(str(error)) from error

    if len(extracted) > MAX_PACKAGE_FILES:
        raise ThemePackageInspectError(f'Theme package exceeds {MAX_PACKAGE_FILES} files')

    files: dict[str, bytes] = {}
    for name, content in extracted.items():
        if is_unsafe_entry_path(name):
            raise ThemePackageInspectError(f'Unsafe path in theme package: {name}')
        if not is_allowed_package_entry(name):
            raise ThemePackageInspectError(f'Disallowed file in theme package: {name}')
        if is_image_entry(name) and len(content) > MAX_IMAGE_BYTES:
            raise ThemePackageInspectError(f'Image too large: {name}')
        if is_motion_entry(name) and len(content) > MAX_MOTION_BYTES:
            raise ThemePackageInspectError(f'Video too large: {name}')
        if is_image_entry(name) and is_animated_image(name, content):
            raise ThemePackageInspectError(f'Animated image is not allowed: {name}')
        if is_motion_entry(name) and not is_valid_mp4(content):
            raise ThemePackageInspectError(f'Invalid MP4 file: {name}')
        files[name] = content

    if RECIPE_JSON not in files:
        raise ThemePackageInspectError('Theme package is missing recipe.json')

    try:
        raw_manifest = json.loads(files[RECIPE_JSON].decode('utf-8'))
        manifest = ThemePackageManifestModel.model_validate(raw_manifest)
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as error:
        raise ThemePackageInspectError(f'Invalid recipe.json: {error}') from error

    warnings: list[str] = []
    can_import = True

    art = manifest.profile.art
    hero_filename = art.assetRef
    poster_filename = art.posterAssetRef
    preview_filename = manifest.previewFile

    if art.mediaKind != 'none' and not hero_filename:
        warnings.append('Art layer enabled but hero asset is missing')
        can_import = False

    if hero_filename and hero_filename not in files:
        warnings.append(f'Hero file not found in package: {hero_filename}')
        can_import = False

    if art.mediaKind == 'video':
        if not poster_filename:
            warnings.append('MP4 themes require a poster image for mobile and reduced-motion fallback')
            can_import = False
        elif poster_filename not in files:
            warnings.append(f'Poster file not found in package: {poster_filename}')
            can_import = False

    if preview_filename and preview_filename not in files:
        warnings.append(f'Preview file not found in package: {preview_filename}')

    session = create_session(
        package_sha256=package_sha256,
        manifest=manifest,
        files=files,
        hero_filename=hero_filename,
        preview_filename=preview_filename if preview_filename in files else None,
        warnings=warnings,
        can_import=can_import,
    )

    hero_thumb = _thumbnail_data_url(files.get(hero_filename or ''), hero_filename)
    if hero_thumb is None and poster_filename and poster_filename in files:
        hero_thumb = _thumbnail_data_url(files[poster_filename], poster_filename)
    preview_thumb = _thumbnail_data_url(
        files.get(preview_filename or ''),
        preview_filename,
    )

    palette = manifest.profile.palette
    return ThemePackageInspectResult(
        session_id=session.session_id,
        package_sha256=package_sha256,
        can_import=can_import,
        warnings=warnings,
        signature_status='unsigned',
        name=manifest.name,
        description=manifest.description,
        tagline=manifest.tagline,
        author=manifest.author,
        layout_id=manifest.profile.layoutId,
        font_id=manifest.profile.fontId,
        media_kind=art.mediaKind,
        wash=art.wash,
        primary_light=palette.primaryLight,
        dual_accent=palette.dualAccent,
        hero_mime=_guess_mime(hero_filename),
        hero_thumbnail_base64=hero_thumb,
        preview_thumbnail_base64=preview_thumb,
    )


def _guess_mime(filename: str | None) -> str | None:
    if not filename:
        return None
    mime, _ = mimetypes.guess_type(filename)
    return mime


def _thumbnail_data_url(content: bytes, filename: str | None) -> str | None:
    if not content or not filename:
        return None
    mime = _guess_mime(filename)
    if mime not in {'image/png', 'image/jpeg', 'image/webp'}:
        return None
    encoded = base64.b64encode(content).decode('ascii')
    return f'data:{mime};base64,{encoded}'
