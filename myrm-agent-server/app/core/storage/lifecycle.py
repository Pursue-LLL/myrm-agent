"""存储生命周期管理

提供全局存储实例注册和优雅关闭机制。
用于确保应用关闭时所有数据安全上传。
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.storage.smart_cache import SmartCachedStorage
    from app.platform_utils.sandbox.storage import S3StorageBackend

logger = logging.getLogger(__name__)

# 全局存储实例注册表
_storage_instances: list["SmartCachedStorage"] = []
_s3_backends: list["S3StorageBackend"] = []


def register_storage(storage: "SmartCachedStorage") -> None:
    """注册存储实例用于优雅关闭

    Args:
        storage: SmartCachedStorage 实例
    """
    _storage_instances.append(storage)
    logger.warning(f"✓ Registered storage instance (total: {len(_storage_instances)})")


def register_s3_backend(backend: "S3StorageBackend") -> None:
    """注册 S3 后端用于优雅关闭（关闭持久化连接）

    Args:
        backend: S3StorageBackend 实例
    """
    _s3_backends.append(backend)
    logger.warning(f"✓ Registered S3 backend (total: {len(_s3_backends)})")


async def shutdown_all_storages(timeout: float = 60.0, force: bool = False) -> None:
    """优雅关闭所有已注册的存储实例

    关闭顺序：
    1. 先关闭 SmartCachedStorage（等待上传队列清空）
    2. 再关闭 S3 后端持久化连接

    Args:
        timeout: 每个存储实例的最大关闭时间（秒）
        force: 是否强制关闭（立即取消所有任务）
    """
    total_instances = len(_storage_instances) + len(_s3_backends)

    if total_instances == 0:
        logger.warning("No storage instances to shutdown")
        return

    logger.warning(
        f"🛑 Shutting down {len(_storage_instances)} cache(s) + {len(_s3_backends)} S3 backend(s) "
        f"(timeout={timeout}s per instance, force={force})"
    )

    # 1. 先关闭 SmartCachedStorage（等待上传队列清空）
    if _storage_instances:
        shutdown_tasks = [storage.shutdown(timeout=timeout, force=force) for storage in _storage_instances]

        results = await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        failure_count = len(results) - success_count

        if failure_count > 0:
            logger.error(f"⚠️ {failure_count} storage instance(s) failed to shutdown gracefully")
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"  Instance {i}: {result}")
        else:
            logger.warning(f"✓ All {success_count} storage instance(s) shut down gracefully")

        _storage_instances.clear()

    # 2. 关闭 S3 后端持久化连接
    if _s3_backends:
        close_tasks = [backend.close() for backend in _s3_backends]

        results = await asyncio.gather(*close_tasks, return_exceptions=True)

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        failure_count = len(results) - success_count

        if failure_count > 0:
            logger.error(f"⚠️ {failure_count} S3 backend(s) failed to close")
        else:
            logger.warning(f"✓ All {success_count} S3 backend(s) closed")

        _s3_backends.clear()


def get_registered_storage_count() -> int:
    """获取已注册的存储实例数量"""
    return len(_storage_instances)
