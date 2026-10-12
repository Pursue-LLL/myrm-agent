"""Pydantic schemas for Shell-Free Safe File Descriptor IPC Pipeline.

[INPUT]
None.

[OUTPUT]
DTO models for safe subprocess dispatching and execution results.

[POS]
Server schemas. Exposes typed contracts for dispatching commands via pure query-files
or stdin stream pipes without shell quotation distortion or injection.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IpcDispatchMode(StrEnum):
    """Transport mechanism for delivering payload without CLI argument injection."""

    QUERY_FILE = "query_file"
    STDIN_STREAM = "stdin_stream"


class IpcCommandDispatchRequest(BaseModel):
    """Request payload to dispatch a subprocess command with external payload."""

    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(..., description="Subprocess executable and arguments (strictly without shell wrappers)")
    payload: str = Field(..., description="Arbitrary unescaped message or query payload text")
    transport: IpcDispatchMode = Field(
        default=IpcDispatchMode.QUERY_FILE,
        description="Delivery transport: 'query_file' (--query-file) or 'stdin_stream'",
    )
    timeout_seconds: float = Field(default=30.0, ge=0.1, le=300.0, description="Process execution timeout in seconds")


class IpcCommandDispatchResponse(BaseModel):
    """Subprocess execution output and telemetry."""

    model_config = ConfigDict(extra="forbid")

    returncode: int = Field(..., description="Process exit code")
    stdout: str = Field(..., description="Captured standard output")
    stderr: str = Field(..., description="Captured standard error")
    duration_seconds: float = Field(..., description="Elapsed execution time in seconds")
    status: str = Field(..., description="Execution status: success, error, timeout, rejected")
