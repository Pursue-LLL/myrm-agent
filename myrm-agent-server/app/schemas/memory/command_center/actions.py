"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryCommandActionRequest, MemoryCommandActionResponse, MemoryCommandRepairActionRequest, MemoryCommandRepairActionResponse

[POS]
Memory command center schemas: command-center action request/response bodies.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryRepairExecutionResult
from pydantic import BaseModel

from .diagnostics import MemoryCommandDiagnosticRun


class MemoryCommandActionRequest(BaseModel):
    """Command center governance action request."""

    target_kind: Literal["pending_memory", "shared_context_proposal", "memory", "conflict_pair"]
    target_id: str = ""
    action: Literal[
        "approve",
        "reject",
        "edit",
        "correct",
        "correct_and_lock",
        "forget",
        "pin",
        "unpin",
        "keep_new",
        "keep_old",
        "coexist",
    ]
    memory_type: str | None = None
    content: str | None = None


class MemoryCommandActionResponse(BaseModel):
    """Command center governance action result."""

    status: Literal["success"]
    target_kind: str
    target_id: str
    action: str


class MemoryCommandRepairActionRequest(BaseModel):
    """Structured Memory Doctor repair execution request."""

    plan_id: Literal[
        "run_diagnostics",
        "run_health_refresh",
        "review_storage_config",
        "enable_vector_store",
        "configure_embedding",
        "review_retrieval_trace",
        "restore_disciplined_defaults",
    ]
    mode: Literal["dry_run", "execute"] = "execute"


class MemoryCommandRepairActionResponse(BaseModel):
    """Structured Memory Doctor repair execution result."""

    result: MemoryRepairExecutionResult
    run: MemoryCommandDiagnosticRun | None = None
