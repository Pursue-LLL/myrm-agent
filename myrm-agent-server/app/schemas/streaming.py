"""Streaming schemas for SSE protocol standardization.

[INPUT]
- myrm_agent_harness.agent.streaming.types::AgentStreamEvent (POS: 底层框架的流式事件模型)

[OUTPUT]
- SSE_RESPONSE_HEADERS: Standard HTTP headers for all SSE endpoints.
- SSEEnvelope: The Pydantic-based SSE envelope enforcing strict JSON structure for the frontend.

[POS]
业务层 SSE 序列化防腐层。保证发送给前端的每个 chunk 符合统一类型。
"""

from pydantic import BaseModel, ConfigDict, Field

SSE_RESPONSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class SSEEnvelope(BaseModel):
    """Strict SSE Envelope to standardize all chunks sent to the frontend."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: str
    data: dict[str, object] | list[object] | str | bool | int | float | None = None
    message_id: str | None = Field(None, alias="messageId")
    error: str | None = None
    error_type: str | None = None
    compression_exhausted: bool | None = None
    
    @classmethod
    def from_any(cls, chunk: object) -> "SSEEnvelope":
        """Convert an arbitrary chunk (dict, Pydantic, Dataclass) to an SSEEnvelope."""
        # Fast path if already string (like pure SSE event formatted outside)
        if isinstance(chunk, str):
            # This should rarely happen in clean architectures, but we must handle legacy strings
            # If it's already an SSE string ("data: ..."), we shouldn't re-wrap it, but from_any expects object -> envelope
            raise ValueError("String chunks should bypass from_any.")
            
        if hasattr(chunk, "to_dict") and callable(chunk.to_dict):
            raw = chunk.to_dict()
        elif hasattr(chunk, "model_dump") and callable(chunk.model_dump):
            raw = chunk.model_dump()
        elif isinstance(chunk, dict):
            raw = chunk
        else:
            import dataclasses
            if dataclasses.is_dataclass(chunk):
                raw = dataclasses.asdict(chunk)
            else:
                raw = {"type": "unknown", "data": str(chunk)}
                
        return cls(**raw)

    def to_sse_chunk(self) -> str:
        """Serialize cleanly to an SSE data chunk."""
        # exclude_none ensures we don't spam the network with null values
        json_str = self.model_dump_json(by_alias=True, exclude_none=True)
        return f"data: {json_str}\n\n"
