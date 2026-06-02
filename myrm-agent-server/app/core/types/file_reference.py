"""文件引用类型定义

用于支持本地模式和 Sandbox 模式的文件引用
"""

from typing import Literal

from pydantic import BaseModel, Field


class FileReference(BaseModel):
    """文件引用

    支持两种模式：
    - 本地模式：直接引用本地文件路径（无需上传）
    - Sandbox 模式：引用已上传的文件 ID
    """

    type: Literal["uploaded", "local_path"] = Field(..., description="文件类型")
    path: str | None = Field(None, description="本地模式：本地绝对路径")
    file_id: str | None = Field(None, description="Sandbox 模式：文件 ID")
    filename: str = Field(..., description="文件名")

    def is_local(self) -> bool:
        """是否为本地文件引用"""
        return self.type == "local_path"

    def is_uploaded(self) -> bool:
        """是否为上传文件引用"""
        return self.type == "uploaded"

    def get_reference_path(self) -> str:
        """获取文件引用路径"""
        if self.is_local() and self.path:
            return self.path
        if self.is_uploaded() and self.file_id:
            return self.file_id
        return ""
