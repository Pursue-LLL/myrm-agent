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
import time

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
APPROVAL_WAIT_SEC = 240.0
GATE_IDLE_FAIL_FAST_SEC = 180.0
# Steer/nudge while agent stream is active but no desktop tool has started yet.
GATE_STREAM_NUDGE_SEC = 45.0
GATE_IDLE_NUDGE_SEC = 30.0
# Hard wall-clock fail-fast for one desktop approval attempt (prevents 7200s empty spin).
DESKTOP_E2E_WALL_CLOCK_FAIL_SEC = 600.0


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
MAX_SEND_ATTEMPTS_SESSION = 3
INFRA_ABORT_MARKERS = (
    "ECONNREFUSED",
    "Could not connect to Chrome",
    "Chrome MCP cleanup failed",
    "immutable test wave is not open",
    "E2E_WAVE_OPEN_FAILED",
    "E2E_RUNTIME_BINDING_FAILED",
    "E2E_WALL_BUDGET_FAIL_FAST",
    "e2e-lite-model-unconfigured",
    "Failed to pin lite model for E2E",
    "LEASE_NOT_ACTIVE",
    "LEASE_CLEANUP_FAILED",
    "upstream request timed out",
    "connection reset",
)
TEXTEDIT_FIXTURE_MARKER = "E2E desktop control scroll target line 1"
E2E_PROMPT = (
    "请帮我在前台 TextEdit 窗口里完成一次桌面操作验证："
    "先用 desktop_snapshot_tool 查看前台结构，"
    "再用 desktop_interact_tool 对 snapshot 里任意 @dref 执行 action=click。"
    "不要使用 desktop_vision。全部完成后只回复 DONE。"
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
    from tests.support.e2e_wall_progress import touch_e2e_wall_progress

    touch_e2e_wall_progress()
    print(f"DESKTOP_E2E: {message}", file=sys.stderr, flush=True)


def assert_desktop_e2e_wall_clock(started_at: float, *, phase: str) -> None:
    elapsed = time.monotonic() - started_at
    if elapsed >= DESKTOP_E2E_WALL_CLOCK_FAIL_SEC:
        raise AssertionError(
            "Desktop E2E wall-clock fail-fast "
            f"({phase}): {elapsed:.0f}s >= {DESKTOP_E2E_WALL_CLOCK_FAIL_SEC:.0f}s "
            "(check LITE_MODEL pin, send button, provider state)"
        )


def max_send_attempts(scope: str) -> int:
    if scope == "always":
        return MAX_SEND_ATTEMPTS_ALWAYS
    if scope == "session":
        return MAX_SEND_ATTEMPTS_SESSION
    return MAX_SEND_ATTEMPTS_ONCE
