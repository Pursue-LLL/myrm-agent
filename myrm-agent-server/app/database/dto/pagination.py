"""[INPUT]
- pydantic / typing (POS: model primitives)

[OUTPUT]
- T, PaginationParams, PaginationMeta, PaginatedResponse

[POS]
Data transfer objects: generic pagination request/meta/response envelope.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """分页查询参数"""

    page: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量，1-100")


class PaginationMeta(BaseModel):
    """分页元数据"""

    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total: int = Field(..., description="总记录数")
    total_pages: int = Field(..., description="总页数")
    has_next: bool = Field(..., description="是否有下一页")
    has_prev: bool = Field(..., description="是否有上一页")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应模型"""

    items: list[T] = Field(..., description="数据列表")
    pagination: PaginationMeta = Field(..., description="分页信息")
