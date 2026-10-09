"""[POS]: app/schemas/tool_backup.py
[INPUT]: Request and response parameters for durable tool use backup index and audit endpoints.
[OUTPUT]: Strongly typed Pydantic models for recording, querying, and auditing tool I/O records.
"""

from pydantic import BaseModel, Field


class RecordToolUseRequest(BaseModel):
    """Request payload to side-index a raw tool execution."""

    session_id: str = Field(..., description="Associated session identifier")
    tool_name: str = Field(..., description="Name of the executed tool")
    raw_input: str = Field(..., description="Exact raw input string or JSON parameters")
    raw_output: str = Field(..., description="Raw output text or observations")
    tool_call_id: str = Field(default="", description="Optional LLM tool call ID")
    status: str = Field(default="success", description="Execution outcome (success or error)")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Tool execution duration in ms")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom contextual metadata tags")


class RecordToolUseResponse(BaseModel):
    """Response payload acknowledging durable tool use registration."""

    id: str = Field(..., description="Unique tool use record identifier")
    session_id: str = Field(..., description="Associated session identifier")
    tool_name: str = Field(..., description="Name of the recorded tool")
    status: str = Field(..., description="Execution outcome status")
    is_truncated: bool = Field(..., description="Whether output payload was truncated")
    created_at_epoch: float = Field(..., description="Epoch timestamp of registration")


class ToolUseItemResponse(BaseModel):
    """Detailed tool use record representation."""

    id: str = Field(..., description="Unique tool use record identifier")
    session_id: str = Field(..., description="Associated session identifier")
    tool_name: str = Field(..., description="Name of the executed tool")
    tool_call_id: str = Field(default="", description="LLM tool call reference ID")
    raw_input: str = Field(..., description="Raw input parameters")
    raw_output: str = Field(..., description="Raw output or observation text")
    status: str = Field(..., description="Execution outcome status")
    duration_ms: float = Field(..., description="Tool execution duration in ms")
    created_at_epoch: float = Field(..., description="Creation epoch timestamp in seconds")
    is_truncated: bool = Field(..., description="Whether payload was truncated")
    original_output_bytes: int = Field(..., description="Original byte length before truncation")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class QueryToolUsesRequest(BaseModel):
    """Filter specifications for auditing tool uses."""

    session_id: str | None = Field(default=None, description="Filter by session identifier")
    tool_name: str | None = Field(default=None, description="Filter by specific tool name")
    status: str | None = Field(default=None, description="Filter by execution outcome (success/error)")
    limit: int = Field(default=50, ge=1, le=500, description="Maximum number of items to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class QueryToolUsesResponse(BaseModel):
    """Response payload containing paginated tool use records."""

    items: list[ToolUseItemResponse] = Field(default_factory=list, description="List of matched tool use items")
    total: int = Field(..., description="Number of items returned in the current page")


class ToolUseStatsResponse(BaseModel):
    """Response payload with aggregate tool use metrics."""

    total_tool_uses: int = Field(..., description="Total tool invocations recorded")
    success_count: int = Field(..., description="Successful invocations")
    error_count: int = Field(..., description="Failed invocations")
    avg_duration_ms: float = Field(..., description="Average invocation duration in ms")
