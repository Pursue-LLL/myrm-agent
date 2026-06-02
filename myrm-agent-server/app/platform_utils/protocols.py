"""平台服务协议定义

定义业务层特有的服务接口。

注意：存储后端协议定义在框架层 (myrm_agent_harness.toolkits.storage.base.StorageProvider)，
业务层直接使用框架层的 StorageProvider，无需重复定义。

使用方式：
    from app.platform_utils.protocols import FileService
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.core.storage.models import File

# =============================================================================
# 文件服务协议
# =============================================================================


@runtime_checkable
class FileService(Protocol):
    """文件服务协议

    处理用户文件的上传、下载、引用等操作。

    实现类：
    - FilesService (Sandbox 模式)
    - LocalFileService (本地模式)
    """

    async def save_file(
        self,
        user_id: str,
        chat_id: str,
        filename: str,
        content: bytes | None = None,
        sandbox_path: str | None = None,
    ) -> "File":
        """保存文件

        Args:
            user_id: 用户 ID
            chat_id: 会话 ID
            filename: 文件名
            content: 文件内容（Sandbox 模式使用）
            sandbox_path: 沙箱路径（本地模式使用）

        Returns:
            文件对象
        """
        ...

    async def get_file(self, file_id: str, user_id: str | None = None) -> "File | None":
        """获取文件信息"""
        ...

    async def get_content(self, file_id: str, user_id: str | None = None) -> bytes:
        """获取文件内容"""
        ...

    async def delete_file(self, file_id: str, user_id: str) -> bool:
        """删除文件"""
        ...

    async def list_files(self, user_id: str) -> "list[File]":
        """列出用户文件"""
        ...


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    "FileService",
]
