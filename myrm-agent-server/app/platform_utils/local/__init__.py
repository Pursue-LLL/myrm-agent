"""本地平台实现

本地桌面模式的所有服务实现。

核心理念：
- 沙箱即存储：文件直接在本地磁盘，无需上传
- 零网络依赖：所有操作都在本地完成
- 简化认证：本地用户，无需 OAuth

注意：存储后端使用框架层的 LocalStorageBackend
    from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
"""

from app.platform_utils.local.file_service import LocalFileService

__all__ = [
    "LocalFileService",
]
