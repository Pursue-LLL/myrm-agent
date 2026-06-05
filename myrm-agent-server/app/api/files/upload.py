"""文件上传 API

通过 FilesService + StorageProvider 统一存储，
支持 Local（本地）和 Sandbox（S3）两种模式。
"""

import io
import logging
import mimetypes

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from myrm_agent_harness.utils.media import ImageCompressor
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.storage import files_service
from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {
    ".png",
    ".jpeg",
    ".jpg",
    ".gif",
    ".webp",
    ".bmp",
    ".pdf",
    ".docx",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".csv",
    ".txt",
    ".md",
    ".json",
}
IMAGE_EXTENSIONS = {".png", ".jpeg", ".jpg", ".gif", ".webp", ".bmp"}


class FileUploadResult(BaseModel):
    file_id: str = Field(..., description="文件 ID")
    file_name: str = Field(..., description="文件名")
    file_url: str = Field(..., description="文件访问 URL")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class FileUploadData(BaseModel):
    uploaded_count: int = Field(..., description="成功上传数量")
    files: list[FileUploadResult] = Field(default=[], description="上传的文件列表")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def _get_file_extension(filename: str) -> str:
    """提取文件扩展名（小写，含点号）"""
    return f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""


def _infer_content_type(filename: str, client_type: str | None) -> str | None:
    """When the client sends a generic or missing MIME type, infer from extension."""
    if client_type and client_type != "application/octet-stream":
        return client_type
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or client_type


def _build_file_content_url(request: Request, file_id: str) -> str:
    """构建文件内容访问 URL"""
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return f"{base_url}{settings.api_prefix}/files/storage/files/{file_id}/content"


async def _compress_image(content: bytes, filename: str) -> bytes:
    """压缩图片，失败时返回原始内容"""
    try:
        original_size = len(content)
        compressor = ImageCompressor()
        # Downsample large images to max 2048px to save LLM tokens and prevent payload explosion
        compressed = compressor.compress(io.BytesIO(content), output_path=None, quality=0.8, max_dimension=2048)
        if isinstance(compressed, bytes) and compressed:
            logger.warning(f"Image compressed: {filename}, original: {original_size} bytes, compressed: {len(compressed)} bytes")
            return compressed
    except Exception as e:
        logger.error(f"Failed to compress image {filename}: {e}")
    return content


@router.post("/upload", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.file_upload)
async def upload_files(
    request: Request,
    files: list[UploadFile] = Form(..., description="要上传的文件列表"),
) -> JSONResponse:
    """上传文件到统一存储服务"""
    if not files:
        raise validation_error("At least one file is required")
    if len(files) > 5:
        raise validation_error("Maximum 5 files allowed")

    # 过滤有效文件
    valid_files: list[tuple[UploadFile, bytes]] = []
    for file in files:
        if not file.filename:
            continue
        ext = _get_file_extension(file.filename)
        if ext not in ALLOWED_EXTENSIONS:
            continue

        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise validation_error(f"File {file.filename} exceeds 10MB limit")
        valid_files.append((file, content))

    if not valid_files:
        raise validation_error("No valid files to upload, please check file types and sizes")

    try:
        results: list[FileUploadResult] = []

        for file, content in valid_files:
            assert file.filename is not None
            ext = _get_file_extension(file.filename)

            # 图片压缩
            if ext in IMAGE_EXTENSIONS:
                content = await _compress_image(content, file.filename)

            # 通过 FilesService 上传到 StorageProvider
            stored_file = await files_service.upload_file(
                filename=file.filename,
                content=content,
                content_type=_infer_content_type(file.filename, file.content_type),
            )

            results.append(
                FileUploadResult(
                    file_id=stored_file.id,
                    file_name=stored_file.filename,
                    file_url=_build_file_content_url(request, stored_file.id),
                )
            )

        data = FileUploadData(uploaded_count=len(results), files=results)
        return success_response(data=data.model_dump())

    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise internal_error(operation="File upload", exception=e) from e
