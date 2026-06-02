"""Shared Context API schemas.

[INPUT]
pydantic::BaseModel (POS: 请求/响应模型基类)

[OUTPUT]
Shared Context CRUD、绑定、写入提案、历史证据提升和迁移响应模型

[POS]
共享上下文 API Schema 层。集中定义 Shared Context 产品接口的数据契约。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SharedContextTargetType = Literal["agent", "channel", "cron", "conversation", "task"]
SharedContextStatus = Literal["active", "archived"]
SharedContextProposalStatus = Literal["pending", "approved", "rejected"]
SharedContextMemoryType = Literal["semantic", "episodic"]
SharedContextMemoryHealthStatus = Literal["ready", "not_configured", "unreachable"]


class SharedContextItem(BaseModel):
    """Shared context response item."""

    id: str
    namespace: str
    name: str
    description: str
    status: SharedContextStatus
    policy: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SharedContextListResponse(BaseModel):
    """Response for listing shared contexts."""

    items: list[SharedContextItem]
    total: int


class SharedContextMemoryHealthResponse(BaseModel):
    """Response for Shared Context memory dependency health."""

    ready: bool
    status: SharedContextMemoryHealthStatus
    model: str
    api_base_configured: bool
    api_key_configured: bool
    probed: bool
    reason: str | None = None
    retryable: bool
    checked_at: datetime
    vector_dimension: int | None = None


class CreateSharedContextRequest(BaseModel):
    """Request to create a shared context."""

    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    policy: dict[str, object] | None = None


class UpdateSharedContextRequest(BaseModel):
    """Request to update a shared context."""

    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    status: SharedContextStatus | None = None
    policy: dict[str, object] | None = None


class SharedContextBindingItem(BaseModel):
    """Shared context binding response item."""

    id: str
    context_id: str
    target_type: SharedContextTargetType
    target_id: str
    created_at: datetime


class SharedContextBindingListResponse(BaseModel):
    """Response for listing shared context bindings."""

    items: list[SharedContextBindingItem]
    total: int


class CreateSharedContextBindingRequest(BaseModel):
    """Request to bind a shared context to a runtime target."""

    target_type: SharedContextTargetType
    target_id: str = Field(..., min_length=1, max_length=255)


class SharedContextWriteProposalItem(BaseModel):
    """Shared context write proposal response item."""

    id: str
    context_id: str
    memory_type: SharedContextMemoryType
    content: str
    metadata: dict[str, object] = Field(default_factory=dict)
    source_type: str
    source_id: str | None = None
    status: SharedContextProposalStatus
    created_at: datetime
    resolved_at: datetime | None = None


class SharedContextWriteProposalListResponse(BaseModel):
    """Response for listing shared context write proposals."""

    items: list[SharedContextWriteProposalItem]
    total: int


class CreateSharedContextWriteProposalRequest(BaseModel):
    """Request to create a shared context write proposal."""

    memory_type: SharedContextMemoryType
    content: str = Field(..., min_length=1, max_length=4000)
    metadata: dict[str, object] | None = None
    source_type: str = Field("manual", min_length=1, max_length=50)
    source_id: str | None = Field(None, max_length=255)


class UpdateSharedContextWriteProposalRequest(BaseModel):
    """Request to edit a pending shared context write proposal before approval."""

    content: str | None = Field(None, min_length=1, max_length=4000)
    metadata: dict[str, object] | None = None


class SharedContextHistoryMessageItem(BaseModel):
    """Chat history message candidate for Shared Context promotion."""

    message_id: str
    chat_id: str
    role: str
    content: str
    snippet: str
    chat_title: str
    sent_at: str | None = None


class SharedContextHistorySearchRequest(BaseModel):
    """Request to search chat history before promoting evidence."""

    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(10, ge=1, le=50)
    offset: int = Field(0, ge=0)
    since: datetime | None = None
    until: datetime | None = None


class SharedContextHistorySearchResponse(BaseModel):
    """Response for Shared Context history search."""

    context_id: str
    query: str
    items: list[SharedContextHistoryMessageItem]
    total: int


class CreateSharedContextProposalFromHistoryRequest(BaseModel):
    """Request to promote a chat history message into a write proposal."""

    message_id: str = Field(..., min_length=1, max_length=255)
    memory_type: SharedContextMemoryType
    content: str | None = Field(None, min_length=1, max_length=4000)
    metadata: dict[str, object] | None = None


class LegacyTeamMemoryMigrationResponse(BaseModel):
    """Response for one-way legacy team memory migration."""

    context: SharedContextItem
    semantic_imported: int
    episodic_imported: int
    skipped: int
