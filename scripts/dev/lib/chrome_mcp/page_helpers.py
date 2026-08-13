"""MCP page lifecycle helpers — retry policies, timeout scaling, stagger.

[INPUT]
dev_gate_contract (POS: Dev Gate v2 合约常量)
mux_load (POS: mux context / wave lease 负载探针)
chrome_mcp_errors (POS: MCP 错误分类谓词)
mcp_protocol (POS: JSON-RPC 解析)
cdp_chat_support (POS: CDP readiness probe)
transport_supervisor (POS: transport exhausted token)

[OUTPUT]
new_page retry/backoff/scaling helpers
parallel peer count detection
CDP drift recovery helpers
tool timeout resolution helpers
reclaim deadline helpers

[POS]
从 chrome_mcp_client.py 提取的 page 生命周期辅助函数。
纯模块级函数，不持有状态，被 ChromeMcpClient 各方法调用。
"""

from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from chrome_mcp.errors import (
    is_transient_mux_error as _is_transient_mux_error,
)
from dev_gate.contract import (
    MUX_CROSS_SESSION_RECOVER_DENIED_TOKEN,
    MUX_RECLAIM_STALL_TOKEN,
    NEW_PAGE_TOOL_RETRY_ATTEMPTS,
    TOOL_RETRY_ATTEMPTS,
    mux_page_reclaim_hard_timeout_sec,
)
from chrome_mcp.protocol import is_retryable_incomplete_new_page_error
from mux.transport_adapter import chrome_e2e_port

if TYPE_CHECKING:
    from chrome_mcp.client import ChromeMcpClient

_LOGGER = logging.getLogger(__name__)
_STALE_MUX_PAGE_TOKEN = "No McpPage found for the given page"
_TOOL_RETRY_ATTEMPTS = TOOL_RETRY_ATTEMPTS
_NEW_PAGE_TOOL_RETRY_ATTEMPTS = NEW_PAGE_TOOL_RETRY_ATTEMPTS


def should_recover_mux_after_tool_error(
    name: str,
    message: str,
    *,
    retry_tools: frozenset[str],
) -> bool:
    if _is_transient_mux_error(message):
        return True
    if name == "new_page" and _STALE_MUX_PAGE_TOKEN in message:
        return True
    if name == "new_page" and is_new_page_cdp_drift_message(message):
        return True
    lowered = message.lower()
    if name in retry_tools and ("timed out" in lowered or "timeout" in lowered):
        return True
    return False


def is_new_page_cdp_drift_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "could not connect to chrome" in lowered
        or "unexpected server response: 404" in lowered
    )


def is_retryable_new_page_parse_exc(
    exc: BaseException,
    new_page_result: dict[str, object] | None,
) -> bool:
    """R229: CDP 404 drift must enter new_page inner retry, not instant re-raise."""
    if isinstance(exc, TimeoutError):
        return True
    if not isinstance(exc, RuntimeError):
        return False
    if is_retryable_incomplete_new_page_error(exc, new_page_result):
        return True
    return is_new_page_cdp_drift_message(str(exc))


def new_page_tool_max_attempts(*, open_page_budget_active: bool) -> int:
    """R121: open_mcp_page wall budget allows one CDP-drift heal + retry."""
    base = tool_retry_attempts("new_page")
    if not open_page_budget_active:
        return base
    return max(2, min(base, 2))


def ensure_cdp_ready_before_parallel_new_page(client: "ChromeMcpClient") -> None:
    """R121: probe CDP before mux new_page when peers>=2."""
    del client
    from cdp_chat.support import wait_e2e_cdp_ready

    peers = parallel_mux_peer_count()
    if peers < 2:
        return
    probe_sec = min(60.0, 20.0 + peers * 5.0)
    if wait_e2e_cdp_ready(timeout_sec=probe_sec):
        return
    raise RuntimeError(
        "CDP endpoint not ready before parallel new_page "
        f"(peers={peers}, port={os.environ.get('MYRM_CHROME_E2E_PORT', '9333')})"
    )


def recover_new_page_chrome_drift(client: "ChromeMcpClient") -> None:
    """Heal CDP 404 on new_page — lightweight shim recover under parallel (R122-B8)."""
    from cdp_chat.support import wait_e2e_cdp_ready

    client._recover_mux_transport()
    if wait_e2e_cdp_ready(timeout_sec=12.0):
        return
    peers = parallel_mux_peer_count()
    if peers >= 2:
        if wait_e2e_cdp_ready(timeout_sec=20.0):
            return
        raise RuntimeError(
            "CDP endpoint not ready after lightweight mux recover under parallel load "
            f"(peers={peers})"
        )
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="new_page chrome cdp 404")
    time.sleep(3.0)
    client._recover_mux_transport()
    if not wait_e2e_cdp_ready(timeout_sec=15.0):
        raise RuntimeError("CDP endpoint not ready after attach restart on 404 drift")


def new_page_retry_attempts() -> int:
    """Scale cold new_page retries under parallel mux/wave load (R112)."""
    peers = parallel_mux_peer_count()
    if peers <= 3:
        return _NEW_PAGE_TOOL_RETRY_ATTEMPTS
    return _NEW_PAGE_TOOL_RETRY_ATTEMPTS + min(3, peers - 3)


def parallel_scaled_page_timeout_ms(base_ms: int) -> int:
    peers = parallel_mux_peer_count()
    if peers <= 3:
        return base_ms
    from mux.load import _MAX_PAGE_TIMEOUT_MS

    scaled = base_ms + (peers - 3) * 20_000
    return min(int(_MAX_PAGE_TIMEOUT_MS * 1.5), scaled)


def is_mux_parallel_fail_fast_message(message: str) -> bool:
    from mux.transport_supervisor import MUX_TRANSPORT_EXHAUSTED_TOKEN

    return (
        MUX_RECLAIM_STALL_TOKEN in message
        or MUX_TRANSPORT_EXHAUSTED_TOKEN in message
        or MUX_CROSS_SESSION_RECOVER_DENIED_TOKEN in message
    )


def parallel_mux_peer_count() -> int:
    """Active parallel mux/wave peers for cross-session teardown guard (R69/TRSM)."""
    from mux.load import snapshot_mux_load

    snapshot = snapshot_mux_load(force=True)
    wave_leases = max(0, snapshot.wave_leases)
    mux_contexts = max(0, snapshot.mux_contexts)
    daemon_count = 1
    try:
        from e2e_core.runtime_probe import mux_owned_daemon_count

        daemon_count = max(1, int(mux_owned_daemon_count()))
    except (ImportError, OSError, TypeError, ValueError):
        pass
    return max(wave_leases, mux_contexts, daemon_count)


def shim_process_alive(client: "ChromeMcpClient") -> bool:
    process = client._process
    return process is not None and process.poll() is None


def reclaim_wall_deadline() -> float:
    return time.monotonic() + float(mux_page_reclaim_hard_timeout_sec())


def remaining_reclaim_sec(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def raise_mux_reclaim_stall(phase: str, *, started: float) -> None:
    elapsed = time.monotonic() - started
    reclaim_cap = mux_page_reclaim_hard_timeout_sec()
    raise RuntimeError(
        f"{MUX_RECLAIM_STALL_TOKEN}: {phase} blocked for {elapsed:.1f}s "
        f"(cap={reclaim_cap}s); recover mux and retry"
    )


def check_mux_reclaim_deadline(
    deadline: float, phase: str, *, started: float
) -> None:
    if time.monotonic() >= deadline:
        raise_mux_reclaim_stall(phase, started=started)


def http_close_exact_target(target_id: str) -> bool:
    target = target_id.strip()
    if not target:
        return False
    url = f"http://127.0.0.1:{chrome_e2e_port()}/json/close/{target}"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            response.read()
        return True
    except urllib.error.HTTPError as exc:
        return exc.code == 404
    except (OSError, urllib.error.URLError):
        return False


def tool_retry_attempts(tool_name: str) -> int:
    if tool_name == "new_page":
        base = _NEW_PAGE_TOOL_RETRY_ATTEMPTS
    else:
        base = _TOOL_RETRY_ATTEMPTS
    peers = parallel_mux_peer_count()
    if peers <= 3:
        return base
    return base + min(3, peers - 3)


def tool_retry_backoff_sec(
    tool_name: str, attempt: int, *, transient: bool
) -> float:
    base = 0.5 * (attempt + 1)
    if tool_name == "new_page":
        base = max(base, 1.0 * (attempt + 1))
    if transient:
        base += 0.75 * (attempt + 1)
    return base


def wave_command_timeout_sec() -> float:
    override = os.environ.get("MYRM_WAVE_CMD_TIMEOUT_SEC", "").strip()
    if override:
        return float(override)
    if os.environ.get("MYRM_E2E_LEASE_ID", "").strip():
        return 120.0
    return 10.0
