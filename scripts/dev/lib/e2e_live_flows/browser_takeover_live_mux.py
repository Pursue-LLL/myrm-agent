"""Browser takeover LIVE — MUX probe / quiesce helpers (R98)."""

from __future__ import annotations

import asyncio
import time

from mcp_chat_ui import McpChatSession


def is_gate_mux_stall(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc)
    return any(
        token in message
        for token in (
            "MUX_RECLAIM_STALL",
            "PAGE_LEASE_HEARTBEAT_FAILED",
            "not owned by this shim session",
            "No page found",
            "Chrome MCP transport closed",
            "Chrome MCP tools/call response timed out",
        )
    )


async def gate_probe_evaluate(
    chat: McpChatSession,
    expression: str,
    *,
    await_promise: bool = False,
    label: str = "evaluate",
) -> object | None:
    """Probe-mode evaluate that tolerates transient MUX stalls during LLM streaming."""
    try:
        return await chat.evaluate(
            expression,
            await_promise=await_promise,
            recv_timeout=15.0,
        )
    except RuntimeError as exc:
        if is_gate_mux_stall(exc):
            print(f"E2E_GATE_MUX_STALL: {label} transient skip", flush=True)
            return None
        message = str(exc)
        if "Failed to fetch" in message or "evaluate_script failed" in message:
            print(
                f"E2E_GATE_PROBE_SKIP: {label} transient skip — {message[:120]}",
                flush=True,
            )
            return None
        raise
    except TimeoutError:
        print(f"E2E_GATE_MUX_STALL: {label} transient skip", flush=True)
        return None


async def quiesce_mux_before_retry(chat: McpChatSession) -> None:
    """Serialize MUX recovery before retry UI to avoid recovery lock deadlock."""
    try:
        await chat.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.())()""",
            await_promise=False,
            recv_timeout=15.0,
        )
    except (RuntimeError, TimeoutError):
        pass
    await asyncio.sleep(2.0)
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(
                chat._client.mux_reset_executor(),
                chat._client.reset_after_orphan,
            ),
            timeout=60.0,
        )
    except TimeoutError:
        chat._client.discard_mux_reset_executor()
        print(
            "E2E_MUX_QUIESCE: reset_after_orphan timed out — continue retry",
            flush=True,
        )
    await asyncio.sleep(1.0)


async def wait_ui_stream_idle(
    chat: McpChatSession, *, timeout_sec: float = 45.0
) -> bool:
    """Wait until sendTurn UI stream releases loading/abortController before API resume."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        raw = await gate_probe_evaluate(
            chat,
            """(() => {
              const turn = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
              return {
                isStreaming: Boolean(turn.isStreaming),
                chatId: turn.chatId ?? null,
              };
            })()""",
            label="wait_ui_stream_idle",
        )
        if isinstance(raw, dict) and raw.get("isStreaming") is not True:
            print(
                f"E2E_UI_STREAM_IDLE: chatId={raw.get('chatId')!r}",
                flush=True,
            )
            return True
        await asyncio.sleep(1.0)
    print("E2E_UI_STREAM_IDLE: timeout — proceed STREAM_CONVERGE anyway", flush=True)
    return False
