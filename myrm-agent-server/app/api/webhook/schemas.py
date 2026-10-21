"""Pydantic schemas for lifecycle outbound webhooks.

[POS] Schemas for creating, updating, listing, and pinging lifecycle webhooks.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LifecycleWebhookCreate(BaseModel):
    """Payload for creating a lifecycle outbound webhook."""

    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=1, max_length=1024)
    secret: str | None = Field(default=None, max_length=255)
    events: list[str] = Field(..., min_length=1)
    agent_id: str | None = Field(default=None)
    is_active: bool = Field(default=True)
    timeout_seconds: int = Field(default=10, ge=1, le=60)


class LifecycleWebhookUpdate(BaseModel):
    """Payload for updating an existing webhook."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, min_length=1, max_length=1024)
    secret: str | None = Field(default=None, max_length=255)
    events: list[str] | None = Field(default=None, min_length=1)
    agent_id: str | None = Field(default=None)
    clear_agent_scope: bool = Field(default=False)
    is_active: bool | None = Field(default=None)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)


class LifecycleWebhookResponse(BaseModel):
    """Output representation of a lifecycle webhook target."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    secret: str | None = None
    has_secret: bool = False
    events: list[str]
    agent_id: str | None = None
    is_active: bool
    timeout_seconds: int
    last_delivery_at: datetime | None = None
    last_delivery_status: int | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class WebhookPingResponse(BaseModel):
    """Response of a test ping probe."""

    success: bool
    status_code: int | None = None
    latency_ms: float
    error: str | None = None
