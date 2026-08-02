"""Export ThemeProfileRecipe + file assets as .myrmtheme ZIP.

[INPUT]
app.core.storage::files_service (POS: 文件存储读取)
app.schemas.theme_profile::ThemeProfileRecipeModel (POS: 主题配方模型)
app.services.theme.package.constants (POS: 包格式常量)
app.services.theme.package.manifest (POS: recipe.json schema)

[OUTPUT]
export_theme_package(recipe) -> bytes: 生成 .myrmtheme ZIP 二进制

[POS]
将 ThemeProfileRecipe + 关联的壁纸/视频资产打包为单一 .myrmtheme ZIP，
资产从 FilesService 按 file: ref 拉取并嵌入 ZIP 根目录。
"""

from __future__ import annotations

import io
import json
import re
import zipfile

from app.core.storage import files_service
from app.schemas.theme_profile import ThemeProfileRecipeModel
from app.services.theme.package.constants import RECIPE_JSON, THEME_PACKAGE_MIN_ENGINE_VERSION, THEME_PACKAGE_SCHEMA_VERSION
from app.services.theme.package.manifest import ThemePackageManifestModel, ThemePackageProfileModel, ThemePackageArtModel


class ThemePackageExportError(ValueError):
    """User-facing export failure."""


_FILE_ID_RE = re.compile(r'^file:(.+)$')


async def export_theme_package(profile: ThemeProfileRecipeModel) -> bytes:
    files: dict[str, bytes] = {}
    hero_name = await _resolve_asset_filename(profile.art.assetRef, files, default_stem='hero')
    poster_name = await _resolve_asset_filename(
        profile.art.posterAssetRef,
        files,
        default_stem='poster',
    )
    preview_name = await _resolve_asset_filename(
        profile.packagePreviewAssetRef,
        files,
        default_stem='preview',
    )
    if preview_name is None and hero_name and hero_name.endswith(('.png', '.jpg', '.jpeg', '.webp')):
        preview_name = hero_name

    art = ThemePackageArtModel(
        focusX=profile.art.focusX,
        focusY=profile.art.focusY,
        wash=profile.art.wash,
        mediaKind=profile.art.mediaKind,
        assetRef=hero_name,
        posterAssetRef=poster_name,
    )
    manifest = ThemePackageManifestModel(
        schemaVersion=THEME_PACKAGE_SCHEMA_VERSION,
        minEngineVersion=THEME_PACKAGE_MIN_ENGINE_VERSION,
        name=profile.name,
        description=profile.packageDescription,
        tagline=profile.packageTagline,
        author=profile.packageAuthor,
        previewFile=preview_name,
        profile=ThemePackageProfileModel(
            name=profile.name,
            layoutId=profile.layoutId,
            fontId=profile.fontId,
            palette=profile.palette,
            art=art,
        ),
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            RECIPE_JSON,
            json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
        )
        for filename, content in files.items():
            archive.writestr(filename, content)
    return buffer.getvalue()


async def _resolve_asset_filename(
    asset_ref: str | None,
    files: dict[str, bytes],
    *,
    default_stem: str,
) -> str | None:
    if not asset_ref:
        return None
    match = _FILE_ID_RE.match(asset_ref)
    if not match:
        raise ThemePackageExportError(f'Unsupported asset ref for export: {asset_ref}')
    file_id = match.group(1)
    metadata = await files_service.get_file(file_id)
    if metadata is None:
        raise ThemePackageExportError(f'Theme asset not found: {file_id}')
    content = await files_service.get_content(file_id)
    filename = _safe_filename(metadata.filename, default_stem=default_stem)
    if filename in files:
        suffix = 2
        stem, ext = _split_ext(filename)
        while f'{stem}-{suffix}{ext}' in files:
            suffix += 1
        filename = f'{stem}-{suffix}{ext}'
    files[filename] = content
    return filename


def _split_ext(filename: str) -> tuple[str, str]:
    if '.' not in filename:
        return filename, ''
    stem, ext = filename.rsplit('.', 1)
    return stem, f'.{ext}'


def _safe_filename(original: str, *, default_stem: str) -> str:
    base = original.replace('\\', '/').split('/')[-1].strip()
    if not base:
        return f'{default_stem}.bin'
    if re.match(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$', base):
        return base
    ext = _split_ext(base)[1] or '.bin'
    return f'{default_stem}{ext}'
