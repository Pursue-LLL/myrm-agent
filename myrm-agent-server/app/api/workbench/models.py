"""[INPUT]
- None (Pydantic models and pure typing)

[OUTPUT]
- TerminalExecRequest & TerminalExecResponse: Command execution payload

[POS]
Data contracts for the auxiliary workbench: a chat workspace's command terminal.
Strict typing: Zero Any.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TerminalExecRequest(BaseModel):
    chat_id: str = Field(..., min_length=1, description="Chat whose workspace the command runs in")
    command: str = Field(..., min_length=1, description="Shell command string")
    cwd: str | None = Field(default=None, description="Working directory inside the chat workspace")
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class TerminalExecResponse(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = Field(default=False, description="Output exceeded the per-stream cap and was cut")
