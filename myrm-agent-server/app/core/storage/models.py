"""文件相关的数据模型

定义文件的数据模型。

注意：FilePurpose 枚举定义在存储层 (myrm_agent_harness.toolkits.storage.types)
     因为它决定了文件的存储路径约定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from myrm_agent_harness.toolkits.storage.types import FilePurpose as FilePurpose
from myrm_agent_harness.utils.coercion import parse_int


@dataclass
class File:
    """文件模型"""

    id: str  # 唯一 ID（如 "file_abc123"）
    purpose: FilePurpose  # 文件用途

    # 文件信息
    filename: str  # 原始文件名
    content_type: str  # MIME 类型
    size: int  # 文件大小（字节）
    storage_path: str  # 存储路径

    # 来源信息（仅 GENERATED 类型）
    source_skill_id: str | None = None  # 生成此文件的技能
    source_chat_id: str | None = None  # 生成此文件的会话

    # 生命周期
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None  # 过期时间

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return {
            "id": self.id,
            "purpose": self.purpose.value,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
            "storage_path": self.storage_path,
            "source_skill_id": self.source_skill_id,
            "source_chat_id": self.source_chat_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "File":
        """从字典创建"""
        purpose = data.get("purpose")
        if isinstance(purpose, str):
            purpose = FilePurpose(purpose)
        elif not isinstance(purpose, FilePurpose):
            purpose = FilePurpose.UPLOAD

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not isinstance(created_at, datetime):
            created_at = datetime.utcnow()

        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        elif not isinstance(expires_at, datetime):
            expires_at = None

        return cls(
            id=str(data.get("id", "")),
            purpose=purpose,
            filename=str(data.get("filename", "")),
            content_type=str(data.get("content_type", "")),
            size=parse_int(data.get("size"), 0),
            storage_path=str(data.get("storage_path", "")),
            source_skill_id=str(data["source_skill_id"]) if data.get("source_skill_id") else None,
            source_chat_id=str(data["source_chat_id"]) if data.get("source_chat_id") else None,
            created_at=created_at,
            expires_at=expires_at,
        )


__all__ = ["File", "FilePurpose"]
