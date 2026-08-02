"""Theme profile recipe models for personalSettings validation.

[INPUT]
(none — pure Pydantic schema)

[OUTPUT]
ThemeProfileRecipeModel: 主题配方模型 (palette + layout + art + font + 市场元数据)
ThemePaletteTokensModel: OKLCh 调色板令牌
ThemeArtConfigModel: 壁纸/视频 Art Layer 配置

[POS]
定义 .myrmtheme 包 recipe 的服务端验证模型，前后端共享 palette/art/font/layout schema。
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ThemeLayoutId = Literal['full-bleed', 'nav-rail-focus', 'chat-hero', 'work-dense']
ThemeMediaKind = Literal['none', 'image', 'video']
ThemeFontId = Literal['inter', 'system', 'atkinson']


class ThemePaletteTokensModel(BaseModel):
    primaryLight: str
    primaryDark: str
    primaryHoverLight: str
    primaryHoverDark: str
    primaryDarkLight: str
    primaryDarkDark: str
    accentWarmLight: str | None = None
    accentWarmDark: str | None = None
    dualAccent: bool


class ThemeArtConfigModel(BaseModel):
    focusX: float = Field(ge=0, le=1)
    focusY: float = Field(ge=0, le=1)
    wash: float = Field(ge=0.2, le=0.8)
    mediaKind: ThemeMediaKind
    assetRef: str | None = None
    posterAssetRef: str | None = None

    @field_validator('assetRef', 'posterAssetRef')
    @classmethod
    def validate_asset_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith('file:'):
            return value
        raise ValueError('Theme asset refs must use file: prefix')


class ThemeProfileRecipeModel(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    layoutId: ThemeLayoutId
    fontId: ThemeFontId
    palette: ThemePaletteTokensModel
    art: ThemeArtConfigModel
    builtin: bool = False
    packageDescription: str | None = Field(default=None, max_length=2000)
    packageTagline: str | None = Field(default=None, max_length=512)
    packageAuthor: str | None = Field(default=None, max_length=256)
    packagePreviewAssetRef: str | None = None

    @field_validator('packagePreviewAssetRef')
    @classmethod
    def validate_package_preview_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith('file:'):
            return value
        raise ValueError('Theme preview asset refs must use file: prefix')
