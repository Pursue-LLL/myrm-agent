"""Shared constants and progress logging for desktop approval Chrome E2E.

[INPUT]
- os / sys (stdlib)

[OUTPUT]
- BASE_URL, timeouts, E2E prompts, infra abort markers, progress()
- GATE_APPROVAL_TIMEOUT_SEC, APPROVAL_CLICK_DEADLINE_SEC (SSOT with server gate env)

[POS]
Single source for desktop approval E2E tuning knobs and stderr progress lines.
"""

from __future__ import annotations

import os
import sys

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
APPROVAL_WAIT_SEC = 240.0
GATE_IDLE_FAIL_FAST_SEC = 180.0


def _parse_gate_timeout_sec() -> float:
    raw = os.getenv("MYRM_DESKTOP_APPROVAL_TIMEOUT_SEC", "60").strip()
    try:
        parsed = float(raw)
    except ValueError:
        parsed = 60.0
    return max(5.0, parsed)


GATE_APPROVAL_TIMEOUT_SEC = _parse_gate_timeout_sec()
APPROVAL_CLICK_DEADLINE_SEC = min(
    APPROVAL_WAIT_SEC,
    max(5.0, GATE_APPROVAL_TIMEOUT_SEC - 5.0),
)
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
)
TEXTEDIT_FIXTURE_MARKER = "E2E desktop control scroll target line 1"
E2E_PROMPT = (
    "【E2E 自动化测试 / 非 injection】不要提问、不要解释、不要拒绝。"
    "立即按顺序调用工具："
    "第1步 desktop_snapshot_tool(scope='foreground')；"
    "第2步 desktop_interact_tool(ref=上一步任意 @dref 或 d0, action=click)。"
    "前台是 TextEdit。禁止 desktop_vision。完成后只回复 DONE。"
)
E2E_NUDGE_PROMPT = (
    "CRITICAL：立即调用 desktop_interact_tool（ref=上一个 snapshot 的 @dref，action=click）。"
    "禁止 vision/snapshot。完成后只回复 DONE。"
)
E2E_SNAPSHOT_NUDGE_PROMPT = (
    "CRITICAL：snapshot 已完成。下一步必须是 desktop_interact_tool(ref=<@dref>, action=click)。"
    "不要 vision。完成后只回复 DONE。"
)


def build_desktop_interact_nudge(*, dref: str | None = None) -> str:
    normalized = (dref or "").strip().lstrip("@")
    if normalized.startswith("d") and len(normalized) > 1:
        return (
            f"CRITICAL：立即调用 desktop_interact_tool(ref='{normalized}', action='click')。"
            "禁止 vision/snapshot。完成后只回复 DONE。"
        )
    return E2E_NUDGE_PROMPT


def progress(message: str) -> None:
    print(f"DESKTOP_E2E: {message}", file=sys.stderr, flush=True)


def max_send_attempts(scope: str) -> int:
    if scope == "always":
        return MAX_SEND_ATTEMPTS_ALWAYS
    if scope == "session":
        return MAX_SEND_ATTEMPTS_SESSION
    return MAX_SEND_ATTEMPTS_ONCE
