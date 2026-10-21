"""文件处理工具函数

提供文件内容读取和 base64 转换功能。
通过 FilesService + StorageProvider 统一存储访问。
"""

import base64
import logging
import mimetypes

logger = logging.getLogger(__name__)


async def read_image_as_base64(url: str) -> tuple[str, str]:
    """读取图片文件并转换为 base64 编码

    从 URL 中提取 file_id，通过 FilesService 读取内容。

    Args:
        url: 文件内容 URL（包含 file_id）

    Returns:
        (base64 编码的图片数据, MIME 类型)

    Raises:
        FileNotFoundError: 文件不存在
    """
    from myrm_agent_harness.utils import extract_file_id_from_url

    file_id = extract_file_id_from_url(url)
    if not file_id:
        raise FileNotFoundError(f"Cannot extract file_id from URL: {url}")

    from app.core.storage import files_service

    file = await files_service.get_file_by_id(file_id)
    if not file:
        raise FileNotFoundError(f"File not found: {file_id}")

    content = await files_service.get_file_content_by_path(file.storage_path)
    if content is None:
        raise FileNotFoundError(f"File content not found: {file_id}")

    mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "image/jpeg"
    base64_data = base64.b64encode(content).decode("utf-8")

    return base64_data, mime_type
