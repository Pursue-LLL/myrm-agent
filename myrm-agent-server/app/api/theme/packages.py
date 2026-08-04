"""Theme package (.myrmtheme) inspect, install, and export API.

[INPUT]
- app.services.theme.package.inspect_service::inspect_theme_package (POS: ZIP 安全解包与 recipe 校验)
- app.services.theme.package.install_service::install_theme_package (POS: 会话消费与 FilesService 资产落盘)
- app.services.theme.package.export_service::export_theme_package (POS: profile + file: 资产打包 ZIP)
- app.core.infra.limiter::limiter (POS: 上传速率限制)

[OUTPUT]
- POST /theme/packages/inspect — 上传 .myrmtheme，返回预览会话与缩略图
- POST /theme/packages/install — 消费 inspect 会话，返回 installed ThemeProfileRecipe
- POST /theme/packages/export — 导出 profile 为 .myrmtheme 下载
- POST /theme/packages/install-from-marketplace — CP 签名的 `.myrmtheme` 直装（Gallery 安装链；响应含 `trustTier`）

[POS]
主题包 HTTP 入口。WebUI Appearance 导入/导出的 server-authoritative 边界。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.schemas.theme_profile import ThemeProfileRecipeModel
from app.services.theme.package.export_service import ThemePackageExportError, export_theme_package
from app.services.theme.package.inspect_service import ThemePackageInspectError, inspect_theme_package
from app.services.theme.package.install_service import ThemePackageInstallError, install_theme_package
from app.services.theme.package.marketplace_install_service import (
    ThemeMarketplaceInstallError,
    install_theme_package_from_marketplace,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ThemePackageInspectData(BaseModel):
    session_id: str
    package_sha256: str
    can_import: bool
    warnings: list[str]
    signature_status: str
    name: str
    description: str | None = None
    tagline: str | None = None
    author: str | None = None
    layout_id: str
    font_id: str
    media_kind: str
    wash: float
    primary_light: str
    dual_accent: bool
    hero_mime: str | None = None
    hero_thumbnail_base64: str | None = None
    preview_thumbnail_base64: str | None = None

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class ThemePackageInstallRequest(BaseModel):
    session_id: str = Field(min_length=1)
    set_active: bool = True
    existing_profile_ids: list[str] = Field(default_factory=list)

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class ThemePackageInstallData(BaseModel):
    profile: ThemeProfileRecipeModel
    set_active: bool
    trust_tier: str | None = None

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def _trust_tier_from_listing_origin(origin: str) -> str:
    normalized = origin.strip().lower()
    return 'verified' if normalized == 'official' else 'community'


class ThemePackageExportRequest(BaseModel):
    profile: ThemeProfileRecipeModel

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post('/packages/inspect', response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.file_upload)
async def inspect_package(
    request: Request,
    file: UploadFile = File(..., description='.myrmtheme ZIP package'),
) -> JSONResponse:
    content = await file.read()
    try:
        result = inspect_theme_package(content)
    except ThemePackageInspectError as error:
        raise validation_error(str(error)) from error

    payload = ThemePackageInspectData(
        session_id=result.session_id,
        package_sha256=result.package_sha256,
        can_import=result.can_import,
        warnings=result.warnings,
        signature_status=result.signature_status,
        name=result.name,
        description=result.description,
        tagline=result.tagline,
        author=result.author,
        layout_id=result.layout_id,
        font_id=result.font_id,
        media_kind=result.media_kind,
        wash=result.wash,
        primary_light=result.primary_light,
        dual_accent=result.dual_accent,
        hero_mime=result.hero_mime,
        hero_thumbnail_base64=result.hero_thumbnail_base64,
        preview_thumbnail_base64=result.preview_thumbnail_base64,
    )
    logger.info('Theme package inspected: session=%s can_import=%s', result.session_id, result.can_import)
    return success_response({'inspect': payload.model_dump(by_alias=True)})


@router.post('/packages/install', response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.file_upload)
async def install_package(
    request: Request,
    body: ThemePackageInstallRequest,
) -> JSONResponse:
    try:
        profile, set_active = await install_theme_package(
            body.session_id,
            set_active=body.set_active,
            existing_profile_ids=set(body.existing_profile_ids),
        )
    except ThemePackageInstallError as error:
        raise validation_error(str(error)) from error

    payload = ThemePackageInstallData(profile=profile, set_active=set_active)
    logger.info('Theme package installed: profile_id=%s', profile.id)
    return success_response({'install': payload.model_dump(by_alias=True)})


@router.post('/packages/export')
@limiter.limit(settings.rate_limit.file_upload)
async def export_package(
    request: Request,
    body: ThemePackageExportRequest,
) -> Response:
    try:
        zip_bytes = await export_theme_package(body.profile)
    except ThemePackageExportError as error:
        raise validation_error(str(error)) from error

    filename = f'{body.profile.id or "theme"}.myrmtheme'.replace('/', '-')
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return Response(content=zip_bytes, media_type='application/zip', headers=headers)


@router.post('/packages/install-from-marketplace', response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.file_upload)
async def install_from_marketplace(
    request: Request,
    listing_id: Annotated[str, Form()],
    package_sha256: Annotated[str, Form()],
    transport_signature: Annotated[str, Form()],
    expires_at: Annotated[float, Form()],
    listing_origin: Annotated[str, Form()] = 'community',
    set_active: Annotated[bool, Form()] = True,
    existing_profile_ids: Annotated[str, Form()] = '[]',
    file: UploadFile = File(..., description='.myrmtheme ZIP from marketplace'),
) -> JSONResponse:
    import json

    content = await file.read()
    try:
        parsed_ids = json.loads(existing_profile_ids)
        id_set = {str(item) for item in parsed_ids} if isinstance(parsed_ids, list) else set()
    except json.JSONDecodeError as error:
        raise validation_error('existing_profile_ids must be a JSON array') from error

    try:
        profile, set_active_result, _signature_status = await install_theme_package_from_marketplace(
            listing_id=listing_id,
            package_bytes=content,
            package_sha256=package_sha256,
            transport_signature=transport_signature,
            expires_at=expires_at,
            set_active=set_active,
            existing_profile_ids=id_set,
        )
    except ThemeMarketplaceInstallError as error:
        raise validation_error(str(error)) from error

    payload = ThemePackageInstallData(
        profile=profile,
        set_active=set_active_result,
        trust_tier=_trust_tier_from_listing_origin(listing_origin),
    )
    logger.info('Theme marketplace package installed: listing=%s profile_id=%s', listing_id, profile.id)
    return success_response({'install': payload.model_dump(by_alias=True)})
