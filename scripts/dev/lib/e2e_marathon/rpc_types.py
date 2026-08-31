"""Shared RPC types for the marathon supervisor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MarathonCommand = Literal["start", "status", "shutdown", "ping"]


@dataclass(frozen=True)
class MarathonRpcResponse:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    state: dict[str, object] | None = None
