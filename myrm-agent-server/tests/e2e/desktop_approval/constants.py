"""Shared constants and progress logging for desktop approval Chrome E2E.

[INPUT]
- os / sys (stdlib)

[OUTPUT]
- BASE_URL, timeouts, E2E prompts, infra abort markers, progress()

[POS]
Single source for desktop approval E2E tuning knobs and stderr progress lines.
"""

from __future__ import annotations

import os
import sys

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
APPROVAL_WAIT_SEC = 240.0
GATE_IDLE_FAIL_FAST_SEC = 60.0
MAX_SEND_ATTEMPTS_ONCE = 3
MAX_SEND_ATTEMPTS_ALWAYS = 3
MAX_SEND_ATTEMPTS_SESSION = 2
INFRA_ABORT_MARKERS = (
    "ECONNREFUSED",
    "Could not connect to Chrome",
    "Chrome MCP cleanup failed",
    "immutable test wave is not open",
    "E2E_WAVE_OPEN_FAILED",
    "E2E_RUNTIME_BINDING_FAILED",
    "LEASE_NOT_ACTIVE",
    "LEASE_CLEANUP_FAILED",
    "upstream request timed out",
    "connection reset",
    "detached Frame",
)
TEXTEDIT_FIXTURE_MARKER = "E2E desktop control scroll target line 1"
E2E_PROMPT = (
    f"TextEdit 已打开，文档含「{TEXTEDIT_FIXTURE_MARKER}」到 line 5。"
    "你必须调用 desktop_interact（ref 来自 snapshot 的 @dref，action=scroll，text=down）。"
    "禁止只调用 desktop_snapshot 或 desktop_vision 就结束。"
    "完成后只回复 DONE。"
)
E2E_NUDGE_PROMPT = (
    "请立即调用 desktop_interact（ref 来自上一个 snapshot 的 @dref，action=scroll，text=down）。"
    "不要只用 snapshot/vision。完成后只回复 DONE。"
)


def progress(message: str) -> None:
    print(f"DESKTOP_E2E: {message}", file=sys.stderr, flush=True)


def max_send_attempts(scope: str) -> int:
    if scope == "always":
        return MAX_SEND_ATTEMPTS_ALWAYS
    if scope == "session":
        return MAX_SEND_ATTEMPTS_SESSION
    return MAX_SEND_ATTEMPTS_ONCE
