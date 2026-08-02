"""Theme workspace media upload API.

[INPUT]
app.config.settings::settings (POS: 全局配置)
app.core.infra.limiter::limiter (POS: 限流器)
app.core.storage::files_service (POS: 文件存储服务)

[OUTPUT]
router: FastAPI APIRouter with POST /assets/upload

[POS]
接收主题壁纸/视频媒体上传，校验类型 (png/jpeg/webp/mp4) 与 80MB 上限，
存入 FilesService 后返回 file_id/content URL。
"""

import logging
import mimetypes

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.storage import files_service
from app.core.utils.errors import validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_THEME_ASSET_BYTES = 80 * 1024 * 1024
_ALLOWED_THEME_EXTENSIONS = {".png", ".jpeg", ".jpg", ".webp", ".mp4"}
_ALLOWED_THEME_MIME = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "video/mp4",
}


class ThemeAssetUploadResult(BaseModel):
    file_id: str = Field(..., description="Theme asset file ID")
    file_name: str = Field(..., description="Original filename")
    file_url: str = Field(..., description="Content URL")
    mime_type: str = Field(..., description="Resolved MIME type")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class ThemeAssetUploadData(BaseModel):
    file: ThemeAssetUploadResult

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def _extension(filename: str) -> str:
    return f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""


def _resolve_mime(filename: str, client_type: str | None) -> str | None:
    if client_type and client_type in _ALLOWED_THEME_MIME:
        return client_type
    guessed, _ = mimetypes.guess_type(filename)
    return guessed


def _build_content_url(request: Request, file_id: str) -> str:
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return f"{base_url}{settings.api_prefix}/files/storage/files/{file_id}/content"


@router.post("/assets/upload", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.file_upload)
async def upload_theme_asset(
    request: Request,
    file: UploadFile = Form(..., description="Theme hero/poster media"),
) -> JSONResponse:
    """Upload theme hero image or MP4 loop for workspace Art Layer."""
    if not file.filename:
        raise validation_error("Filename is required")

    ext = _extension(file.filename)
    if ext not in _ALLOWED_THEME_EXTENSIONS:
        raise validation_error(f"Unsupported theme media type: {ext}")

    mime = _resolve_mime(file.filename, file.content_type)
    if mime not in _ALLOWED_THEME_MIME:
        raise validation_error(f"Unsupported theme MIME type: {mime}")

    content = await file.read()
    if len(content) > _MAX_THEME_ASSET_BYTES:
        raise validation_error("Theme media exceeds 80MB limit")
    if not content:
        raise validation_error("Empty file")

    stored = await files_service.upload_file(
        filename=file.filename,
        content=content,
        content_type=mime,
    )
    file_id = stored.id
    payload = ThemeAssetUploadData(
        file=ThemeAssetUploadResult(
            file_id=file_id,
            file_name=stored.filename,
            file_url=_build_content_url(request, file_id),
            mime_type=mime,
        )
    )
    logger.info("Theme asset uploaded: %s (%s bytes)", file_id, len(content))
    return success_response(payload.model_dump(by_alias=True))
