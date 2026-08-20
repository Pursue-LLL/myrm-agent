"""recipe.json schema for .myrmtheme packages (pre-install relative asset paths).

[INPUT]
app.schemas.theme_profile (POS: 共享类型定义)

[OUTPUT]
ThemePackageManifestModel: recipe.json 顶层模型 (schema + engine + profile)
to_installed_profile(manifest, asset_map) -> ThemeProfileRecipeModel

[POS]
定义 .myrmtheme ZIP 内 recipe.json 的 Pydantic 模型，
to_installed_profile 将包内相对路径替换为 file: ref 后输出安装态 recipe。
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.theme_profile import (
    ThemeArtConfigModel,
    ThemeFontId,
    ThemeLayoutId,
    ThemeMediaKind,
    ThemePaletteTokensModel,
    ThemeProfileRecipeModel,
)

_RELATIVE_ASSET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ThemePackageArtModel(BaseModel):
    focusX: float = Field(ge=0, le=1)
    focusY: float = Field(ge=0, le=1)
    wash: float = Field(ge=0.2, le=0.8)
    mediaKind: ThemeMediaKind
    assetRef: str | None = None
    posterAssetRef: str | None = None

    @field_validator("assetRef", "posterAssetRef")
    @classmethod
    def validate_relative_asset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("file:"):
            raise ValueError("Package art refs must be relative filenames, not file: URLs")
        if not _RELATIVE_ASSET_RE.match(value):
            raise ValueError(f"Invalid package asset filename: {value}")
        return value


class ThemePackageProfileModel(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    layoutId: ThemeLayoutId
    fontId: ThemeFontId
    palette: ThemePaletteTokensModel
    art: ThemePackageArtModel


class ThemePackageManifestModel(BaseModel):
    schemaVersion: Literal[1]
    minEngineVersion: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)
    tagline: str | None = Field(default=None, max_length=512)
    author: str | None = Field(default=None, max_length=256)
    previewFile: str | None = None
    profile: ThemePackageProfileModel

    @field_validator("previewFile")
    @classmethod
    def validate_preview_file(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _RELATIVE_ASSET_RE.match(value):
            raise ValueError(f"Invalid preview filename: {value}")
        return value


def to_installed_profile(
    manifest: ThemePackageManifestModel,
    *,
    profile_id: str,
    hero_file_id: str | None,
    poster_file_id: str | None,
    preview_file_id: str | None,
) -> ThemeProfileRecipeModel:
    art = manifest.profile.art
    return ThemeProfileRecipeModel(
        id=profile_id,
        name=manifest.profile.name,
        layoutId=manifest.profile.layoutId,
        fontId=manifest.profile.fontId,
        palette=manifest.profile.palette,
        art=ThemeArtConfigModel(
            focusX=art.focusX,
            focusY=art.focusY,
            wash=art.wash,
            mediaKind=art.mediaKind,
            assetRef=f"file:{hero_file_id}" if hero_file_id else None,
            posterAssetRef=f"file:{poster_file_id}" if poster_file_id else None,
        ),
        builtin=False,
        packageDescription=manifest.description,
        packageTagline=manifest.tagline,
        packageAuthor=manifest.author,
        packagePreviewAssetRef=f"file:{preview_file_id}" if preview_file_id else None,
    )
