"""文件管理 API

提供文件的上传、下载、删除接口。
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from myrm_agent_harness.toolkits.storage.types import FilePurpose
from pydantic import BaseModel

from app.core.storage import files_service
from app.core.storage.models import File as FileModel

logger = logging.getLogger(__name__)

router = APIRouter()


# 请求/响应模型
class FileResponse(BaseModel):
    """文件响应"""

    id: str
    purpose: str
    filename: str
    content_type: str
    size: int
    storage_path: str
    source_skill_id: str | None
    source_chat_id: str | None
    created_at: str
    expires_at: str | None

    @classmethod
    def from_model(cls, file: FileModel) -> "FileResponse":
        """从 File 模型创建响应"""
        return cls(
            id=file.id,
            purpose=file.purpose.value,
            filename=file.filename,
            content_type=file.content_type,
            size=file.size,
            storage_path=file.storage_path,
            source_skill_id=file.source_skill_id,
            source_chat_id=file.source_chat_id,
            created_at=file.created_at.isoformat(),
            expires_at=file.expires_at.isoformat() if file.expires_at else None,
        )


class FileListResponse(BaseModel):
    """文件列表响应"""

    files: list[FileResponse]
    total: int


class UploadFileResponse(BaseModel):
    """上传文件响应"""

    file_id: str
    filename: str
    content_type: str
    size: int


# API 端点
@router.post("/files/upload", response_model=UploadFileResponse)
async def upload_file(
    file: UploadFile = File(...),
) -> UploadFileResponse:
    """上传文件

    Args:
        file: 上传的文件

    Returns:
        上传结果
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if file.size is not None and file.size > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds 100MB limit")

    content = await file.read()

    result = await files_service.upload_file(
        filename=file.filename,
        content=content,
        content_type=file.content_type,
    )

    return UploadFileResponse(
        file_id=result.id,
        filename=result.filename,
        content_type=result.content_type,
        size=result.size,
    )


@router.get("/files", response_model=FileListResponse)
async def list_files(
    purpose: str | None = None,
    include_expired: bool = False,
) -> FileListResponse:
    """列出用户的文件

    Args:
        purpose: 文件用途过滤（upload/generated）
        include_expired: 是否包含过期文件

    Returns:
        文件列表
    """
    file_purpose = None
    if purpose:
        try:
            file_purpose = FilePurpose(purpose)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid file purpose: {purpose}") from e

    files = await files_service.list_files(
        purpose=file_purpose,
        include_expired=include_expired,
    )

    return FileListResponse(
        files=[FileResponse.from_model(f) for f in files],
        total=len(files),
    )


@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str,
) -> FileResponse:
    """获取文件信息

    Args:
        file_id: 文件 ID

    Returns:
        文件信息
    """
    file = await files_service.get_file(file_id)
    if not file:
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

    return FileResponse.from_model(file)


@router.get("/files/{file_id}/content")
async def get_file_content(
    file_id: str,
    inline: bool = True,
) -> Response:
    """获取文件内容

    Args:
        file_id: 文件 ID
        inline: 是否在浏览器中内联显示（默认 True，用于预览）

    Returns:
        文件内容
    """
    logger.info(f"[API] 获取文件内容: file_id={file_id}, inline={inline}")

    file = await files_service.get_file_by_id(file_id)

    if not file:
        logger.warning(f"[API] 文件未找到: file_id={file_id}")
        raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

    # 获取文件内容
    try:
        content = await files_service.get_file_content_by_path(file.storage_path)
        if content is None:
            raise HTTPException(status_code=404, detail=f"File content not found: {file_id}")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    # 根据 inline 参数决定 Content-Disposition
    # inline: 在浏览器中显示（用于预览）
    # attachment: 触发下载
    disposition = "inline" if inline else "attachment"

    return Response(
        content=content,
        media_type=file.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{file.filename}"',
        },
    )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: str,
) -> dict[str, str]:
    """删除文件

    Args:
        file_id: 文件 ID

    Returns:
        删除结果
    """
    try:
        success = await files_service.delete_file(file_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
        return {"message": "File deleted successfully"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


# 管理端点
@router.post("/admin/files/cleanup")
async def cleanup_expired_files() -> dict[str, int]:
    """清理过期文件（管理员）

    Returns:
        清理的文件数量
    """
    cleaned = await files_service.cleanup_expired_files()
    return {"cleaned_count": cleaned}
