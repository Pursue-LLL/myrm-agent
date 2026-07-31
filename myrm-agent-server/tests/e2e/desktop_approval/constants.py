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


def _parse_stream_stuck_sec() -> float:
    raw = os.getenv("MYRM_DESKTOP_E2E_STREAM_STUCK_SEC", "120").strip()
    try:
        parsed = float(raw)
    except ValueError:
        parsed = 120.0
    return max(60.0, parsed)


GATE_STREAM_STUCK_SEC = _parse_stream_stuck_sec()
GATE_PENDING_GRACE_SEC = 30.0
# After first observed desktop_interact_tool, hand off to banner phase if
# pending gate still not registered within this window.
GATE_INTERACT_HANDOFF_SEC = 12.0
# Steer/nudge while agent stream is active but no desktop tool has started yet.
GATE_STREAM_NUDGE_SEC = 45.0
GATE_IDLE_NUDGE_SEC = 30.0
# After snapshot + nudge, fail-fast if model still loops snapshot without interact.
GATE_SNAPSHOT_LOOP_FAIL_SEC = 60.0
# Hard wall-clock fail-fast for one desktop approval attempt.
# 200s per attempt × 2 attempts + 60s bootstrap < 600s pytest-timeout.
# Signoff may queue behind parallel SHPOIB; allow extra slack without exceeding 600s leg.
def _resolve_desktop_e2e_wall_clock_fail_sec() -> float:
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        base = 280.0
        if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in ("1", "true", "yes"):
            try:
                from cdp_chat_support import signoff_parallel_desktop_wall_clock_fail_sec

                return signoff_parallel_desktop_wall_clock_fail_sec(base)
            except ImportError:
                return base
        return base
    return 200.0


DESKTOP_E2E_WALL_CLOCK_FAIL_SEC = _resolve_desktop_e2e_wall_clock_fail_sec()


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
MAX_SEND_ATTEMPTS_ONCE = 2
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
)
TEXTEDIT_FIXTURE_MARKER = "E2E desktop control scroll target line 1"
E2E_PROMPT = (
    "INSTRUCTION: You MUST call tools. Do NOT reply with text only.\n"
    "Step 1: Call desktop_snapshot_tool(scope='foreground') to capture the screen.\n"
    "Step 2: Call desktop_interact_tool(ref=@d1, action='click') to click the first line.\n"
    "Step 3: Reply exactly: DONE\n"
    "Context: A TextEdit window with sample text is in the foreground."
)
E2E_NUDGE_PROMPT = (
    "MANDATORY: Call a tool NOW. Do NOT output text without a tool call.\n"
    "If you have @drefs: call desktop_interact_tool(ref=@d1, action='click').\n"
    "If you have NO @drefs: call desktop_snapshot_tool(scope='foreground') first.\n"
    "Do NOT call desktop_vision_tool. Reply DONE after tool calls."
)
E2E_SNAPSHOT_NUDGE_PROMPT = (
    "IMPORTANT: You already have a snapshot with element references. "
    "Do NOT take another snapshot. "
    "Call desktop_interact_tool now to click one of the text elements "
    "using its ref (like @d1 or @d2). Then reply DONE."
)
E2E_VISION_CORRECT_PROMPT = (
    "Stop. Call desktop_snapshot_tool(scope='foreground') to get @drefs for the front app, "
    "then call desktop_interact_tool(ref=@dref, action='click') to click one line in TextEdit. "
    "If snapshot still has no usable @dref, immediately call "
    "desktop_vision_tool(action='left_click', coordinate=[640, 360]) to request desktop control approval, "
    "then retry desktop_snapshot_tool(scope='foreground') and desktop_interact_tool. "
    "Do not use bash or text-only explanations. Reply DONE after a desktop control tool call."
)
E2E_SNAPSHOT_RESEED_PROMPT = (
    "If desktop_snapshot_tool reports no active desktop or returns no @drefs, "
    "call desktop_vision_tool once to re-seed desktop context for TextEdit. "
    "Then call desktop_snapshot_tool(scope='foreground') and immediately call "
    "desktop_interact_tool(ref=@dref, action='click') on a TextEdit line. "
    "If @drefs are still missing, call desktop_vision_tool(action='left_click', coordinate=[640, 360]) "
    "to force the approval gate, then retry snapshot + interact. "
    "Do not finish before a desktop control tool call runs. Reply DONE."
)


def build_desktop_interact_nudge(*, dref: str | None = None) -> str:
    normalized = (dref or "").strip().lstrip("@")
    if normalized.startswith("d") and len(normalized) > 1:
        return (
            f"MANDATORY TEST ACTION: Call desktop_interact_tool(ref=@{normalized}, action='click') NOW "
            "as your first tool call. "
            "Do NOT call desktop_snapshot_tool or desktop_vision_tool before this interact call. "
            f"If the call errors, retry desktop_interact_tool(ref=@{normalized}, action='click') once. "
            "Do not output explanations before tool calls. "
            "Reply DONE only after desktop_interact_tool is called."
        )
    return E2E_NUDGE_PROMPT


def progress(message: str) -> None:
    from tests.support.e2e_wall_progress import touch_e2e_wall_progress

    touch_e2e_wall_progress()
    print(f"DESKTOP_E2E: {message}", file=sys.stderr, flush=True)


def assert_desktop_e2e_wall_clock(started_at: float, *, phase: str) -> None:
    elapsed = time.monotonic() - started_at
    cap_sec = _resolve_desktop_e2e_wall_clock_fail_sec()
    if elapsed >= cap_sec:
        raise AssertionError(
            "Desktop E2E wall-clock fail-fast "
            f"({phase}): {elapsed:.0f}s >= {cap_sec:.0f}s "
            "(check LITE_MODEL pin, send button, provider state)"
        )


def max_send_attempts(scope: str) -> int:
    if scope == "always":
        return MAX_SEND_ATTEMPTS_ALWAYS
    if scope == "session":
        return MAX_SEND_ATTEMPTS_SESSION
    return MAX_SEND_ATTEMPTS_ONCE
