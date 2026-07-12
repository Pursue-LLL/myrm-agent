"""Shared RPC types for the stack supervisor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RpcCommand = Literal["ensure", "attach", "reset", "status", "ping", "shutdown"]


@dataclass(frozen=True)
class RpcResponse:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    state: dict[str, object] | None = None
