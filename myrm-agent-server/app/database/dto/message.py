"""[INPUT]
- pydantic / typing (POS: model primitives)

[OUTPUT]
- MessageBase, MessageDTO, MessageCreate, MessageResponse, CursorPage

[POS]
Data transfer objects: message DTOs and the message cursor page.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MessageBase(BaseModel):
    """消息基础模型"""

    role: str = Field(..., description="消息角色：user或assistant")
    content: str = Field(..., description="消息内容")
    metadata: dict[str, Any] | None = Field(default=None, description="消息元数据")


class MessageDTO(BaseModel):
    """消息领域对象 (Domain Transfer Object)
    用于替代 SQLAlchemy 的 Message 模型，在业务层传递。
    """

    id: str
    chat_id: str
    role: str
    content: str
    sent_at: datetime
    sent_timezone: str
    created_at: datetime
    extra_data: dict[str, Any] | None = None
    sibling_group_id: str | None = None
    is_active: bool = True
    sibling_count: int = 0
    sibling_index: int = 0

    model_config = {"from_attributes": True}


class MessageCreate(MessageBase):
    """创建消息请求模型"""

    messageId: str = Field(..., description="消息ID")
    chatId: str = Field(..., description="聊天会话ID")
    createdAt: datetime | None = Field(default=None, description="创建时间")

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def handle_extra_fields(cls, data: dict[str, Any]) -> dict[str, Any]:
        """将额外字段移动到metadata中"""
        if not isinstance(data, dict):
            return data

        # 定义标准字段
        standard_fields = {
            "messageId",
            "chatId",
            "createdAt",
            "role",
            "content",
            "metadata",
        }

        # 提取额外字段
        extra_fields = {}
        cleaned_data = {}

        for key, value in data.items():
            if key in standard_fields:
                cleaned_data[key] = value
            else:
                extra_fields[key] = value

        # 将额外字段合并到metadata中
        if extra_fields:
            existing_metadata = cleaned_data.get("metadata", {})
            if isinstance(existing_metadata, dict):
                existing_metadata.update(extra_fields)
            else:
                existing_metadata = extra_fields
            cleaned_data["metadata"] = existing_metadata

        return cleaned_data


class MessageResponse(MessageBase):
    """消息响应模型"""

    messageId: str = Field(..., description="消息ID")
    chatId: str = Field(..., description="聊天会话ID")
    createdAt: datetime = Field(..., description="创建时间")
    siblingGroupId: str | None = Field(default=None, description="Sibling group ID for regenerated responses")
    siblingCount: int = Field(default=0, description="Total siblings in group")
    siblingIndex: int = Field(default=0, description="Current message index in sibling group (1-based)")

    model_config = ConfigDict(from_attributes=True)


class CursorPage(BaseModel):
    """Cursor-based paginated messages response."""

    messages: list[MessageResponse] = Field(..., description="消息列表（按时间升序）")
    has_more: bool = Field(..., description="是否有更早的消息")
    next_cursor: str | None = Field(default=None, description="下一页游标（最早一条消息的 ID）")
