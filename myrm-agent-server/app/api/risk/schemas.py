"""Risk governance API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuleCreateRequest(BaseModel):
    rule_id: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    pattern: str = Field(..., min_length=1)
    severity: str = Field(..., pattern=r"^(low|medium|high)$")
    action: str = Field(..., pattern=r"^(allow|block)$")
    category: str = Field(default="custom")
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)


class RuleUpdateRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    pattern: str | None = Field(None, min_length=1)
    severity: str | None = Field(None, pattern=r"^(low|medium|high)$")
    action: str | None = Field(None, pattern=r"^(allow|block)$")
    category: str | None = None
    is_enabled: bool | None = None
    sort_order: int | None = Field(None, ge=0)


class BatchToggleRequest(BaseModel):
    rule_ids: list[str] = Field(..., min_length=1)
    is_enabled: bool


class BatchImportRequest(BaseModel):
    rules: list[RuleCreateRequest] = Field(..., min_length=1, max_length=200)


class RuleTestRequest(BaseModel):
    pattern: str = Field(..., min_length=1)
    test_text: str = Field(..., min_length=1)
