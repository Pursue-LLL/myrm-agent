"""Sandbox 平台实现

沙箱模式的服务实现，由控制平面管理的隔离运行环境。

核心理念：
- 云存储：文件上传到 S3/R2
- 容器化执行：由 myrm-control-plane 管理
- 完整身份：由控制平面注入单租户身份

组件：
- S3StorageBackend: S3/R2 云存储后端
- FilesService: 直接使用 app/core/storage/service.py（实现 FileService Protocol）
"""

import logging

from app.platform_utils.sandbox.storage import S3StorageBackend

logger = logging.getLogger(__name__)


def create_s3_storage() -> S3StorageBackend:
    """从 AppSettings 创建 S3 存储后端。

    Raises:
        ValueError: 缺少必需的 S3 配置
    """
    from app.config.settings import settings

    s = settings.storage
    endpoint_url = s.s3_endpoint_url
    access_key = s.aws_access_key_id.get_secret_value()
    secret_key = s.aws_secret_access_key.get_secret_value()

    if not all([endpoint_url, access_key, secret_key]):
        raise ValueError(
            "Sandbox mode requires S3 configuration. Please set: S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
        )

    backend = S3StorageBackend(
        bucket=s.s3_bucket_name,
        prefix="",
        region=s.s3_region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint_url,
    )
    logger.warning("S3 storage initialized (bucket=%s)", s.s3_bucket_name)
    return backend


__all__ = ["S3StorageBackend", "create_s3_storage"]
