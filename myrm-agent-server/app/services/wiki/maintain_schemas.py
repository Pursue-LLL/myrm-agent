"""
[INPUT] (none)
[OUTPUT] WikiMaintainState, WikiMaintainRunResult: wiki 维护定时任务状态与运行结果
[POS] Wiki 维护 cron 的 Pydantic 模型。定义状态持久化和运行结果的数据结构。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WikiMaintainModeLiteral = Literal["structural", "full"]


class WikiMaintainState(BaseModel):
    last_run_at: datetime | None = None
    last_mode: WikiMaintainModeLiteral | None = None
    last_issues_found: int = 0
    last_issues_fixed: int = 0
    last_connections_discovered: int = 0
    last_duration_ms: int = 0
    last_skipped_reason: str | None = None
    last_output: str | None = None


class WikiMaintainRunResult(BaseModel):
    skipped: bool = False
    skipped_reason: str | None = None
    mode: WikiMaintainModeLiteral = "structural"
    issues_found: int = 0
    issues_fixed: int = 0
    connections_discovered: int = 0
    duration_ms: int = 0
    raw_security_removed: int = 0
    raw_security_removed_paths: list[str] = Field(default_factory=list)
    summary_text: str = "[SILENT]"
