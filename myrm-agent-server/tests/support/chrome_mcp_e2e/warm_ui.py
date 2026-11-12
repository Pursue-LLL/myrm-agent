"""Warm the shared UI before a page opens: route warm-up plus the attach-time frontend heal and client warm-up."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from cdp_chat.support import get_e2e_ui_url
from dev_gate.contract import attach_ui_heal_ensure_subprocess_sec as _attach_ui_heal_ensure_subprocess_sec
from e2e_core.orchestrator import touch_wall_progress
from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled, shared_ui_hydrate_slot
from e2e_core.warm_ui_heal import heal_shared_frontend_debounced

from tests.support.e2e_runtime_guard import heartbeat_once

from .parallel_load import _parallel_chrome_e2e_active, _warm_ui_parallel_wait_sec


def warm_ui_route(path: str, *, timeout_sec: float | None = None) -> None:
    """HTTP GET a UI route so webpack/turbopack compiles before Chrome navigation."""
    import os

    if not path.startswith("/"):
        raise ValueError(f"warm_ui_route expects an absolute path, got: {path!r}")
    url = f"{get_e2e_ui_url()}{path}"
    try:
        from e2e_core.warm_shell_registry import platform_shell_fresh

        if platform_shell_fresh(route_path=path):
            heartbeat_once()
            touch_wall_progress(current_node="warm_ui_route_skipped_registry_reuse")
            request = urllib.request.Request(url, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=5.0) as response:
                    if int(response.status) == 200:
                        return
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
            ):
                pass
    except ImportError:
        pass
    base_wait = timeout_sec if timeout_sec is not None else float(os.environ.get("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "180"))
    wait_sec = _warm_ui_parallel_wait_sec(base_wait)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        wait_sec = min(wait_sec, 120.0)
    poll_sec = float(os.environ.get("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "2"))
    attempt_cap_sec = float(os.environ.get("MYRM_CHROME_E2E_WARM_ATTEMPT_SEC", "45"))
    deadline = time.monotonic() + wait_sec
    last_error: BaseException | None = None
    heal_interval = 30.0
    next_heal_at = time.monotonic() + heal_interval
    monorepo_root = Path(__file__).resolve().parents[5]

    def _heal_shared_frontend() -> None:
        if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
            return
        try:
            from e2e_core.warm_ui_heal import launch_force_blocks_frontend_heal

            if launch_force_blocks_frontend_heal():
                return
        except ImportError:
            if os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1":
                return
        heal_timeout = float(_attach_ui_heal_ensure_subprocess_sec())
        try:
            from mux.transport_supervisor import parallel_active_test_count

            if parallel_active_test_count() > 1:
                heal_timeout = float(_attach_ui_heal_ensure_subprocess_sec(1))
        except ImportError:
            pass
        heal_shared_frontend_debounced(
            monorepo_root,
            debounce_sec=60.0,
            subprocess_timeout_sec=heal_timeout,
        )

    def _attempt_warm_get() -> bool:
        """Single GET attempt; True when HTTP 200."""
        nonlocal last_error, next_heal_at
        try:
            from e2e_session_runtime.heartbeat import shell_heartbeat_loop_active
        except ImportError:
            shell_heartbeat_loop_active = None  # type: ignore[misc, assignment]
        if shell_heartbeat_loop_active is not None and shell_heartbeat_loop_active():
            touch_wall_progress(current_node="warm_ui_route")
        else:
            heartbeat_once()
        if time.monotonic() >= next_heal_at:
            next_heal_at = time.monotonic() + heal_interval
            _heal_shared_frontend()
        request = urllib.request.Request(  # noqa: S310 - loopback only
            url, method="GET"
        )
        # A cold Next dev compile of "/" routinely exceeds 10s on a loaded host; a shorter
        # per-attempt timeout abandons every request before the compile can finish.
        per_attempt = max(3.0, min(attempt_cap_sec, deadline - time.monotonic()))

        def _do_get() -> int:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=per_attempt
            ) as response:
                return int(response.status)

        try:
            if parallel_shared_ui_hydrate_queue_enabled():
                with shared_ui_hydrate_slot():
                    status = _do_get()
            else:
                status = _do_get()
            if status == 200:
                return True
            last_error = RuntimeError(f"warm_ui_route GET {url} returned HTTP {status}")
            if status in {404, 502, 503}:
                _heal_shared_frontend()
                next_heal_at = time.monotonic() + heal_interval
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 502, 503}:
                last_error = exc
                # Nested /settings/* often 404 on HTTP GET pre-orchestrator-navigate — heal cannot fix (85292).
                if exc.code == 404 and path.startswith("/settings"):
                    return False
                _heal_shared_frontend()
                next_heal_at = time.monotonic() + heal_interval
            else:
                last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            _heal_shared_frontend()
            next_heal_at = time.monotonic() + heal_interval
        return False

    def _warm_ui_poll_loop() -> None:
        while time.monotonic() < deadline:
            if _attempt_warm_get():
                return
            time.sleep(poll_sec)
        warm_error = RuntimeError(f"warm_ui_route GET {url} failed after {wait_sec:.0f}s: {last_error!r}")
        if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
            print(
                f"E2E_WARM_UI_SOFT_SKIP: signoff defers compile to Chrome bootstrap — {warm_error}",
                file=sys.stderr,
                flush=True,
            )
            touch_wall_progress(current_node="warm_ui_route_soft_skip")
            return
        raise warm_error

    _warm_ui_poll_loop()


def _settings_http_warm_skippable(route_path: str) -> bool:
    """Skip redundant HTTP warm when bootstrap hot path + registry shell are fresh."""
    hot = os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip()
    if hot not in {"reused", "fast_create", "transaction"}:
        return False
    shell_route = "/settings" if route_path.startswith("/settings/") and route_path != "/settings" else route_path
    try:
        from e2e_core.warm_shell_registry import platform_shell_fresh

        return platform_shell_fresh(route_path=shell_route)
    except ImportError:
        return hot == "reused"


_ATTACH_CLIENT_WARMUP_URLS: set[str] = set()
_ATTACH_FRONTEND_HEAL_TRIGGERED = False


def _trigger_attach_frontend_heal_once() -> None:
    """Restart Turbopack when HTTP 200 shell persists without client hydration (body SSOT)."""
    global _ATTACH_CLIENT_WARMUP_URLS, _ATTACH_FRONTEND_HEAL_TRIGGERED
    if os.environ.get("MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH", "").strip() == "1":
        return
    if _ATTACH_FRONTEND_HEAL_TRIGGERED:
        return
    try:
        from e2e_core.warm_ui_heal import launch_force_blocks_frontend_heal

        if launch_force_blocks_frontend_heal():
            return
    except ImportError:
        if os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1":
            return
    _ATTACH_FRONTEND_HEAL_TRIGGERED = True
    monorepo_root = Path(__file__).resolve().parents[5]
    try:
        from e2e_core.warm_ui_heal import heal_shared_frontend_attach

        touch_wall_progress(current_node="attach_frontend_heal")
        flock_wait = 8.0 if _parallel_chrome_e2e_active() else 45.0
        heal_shared_frontend_attach(
            monorepo_root,
            flock_wait_sec=flock_wait,
            # SSOT budget: a cold Turbopack compile runs 85s–282s, so a hardcoded 90s
            # child timeout killed healthy compiles and looped the heal forever.
            subprocess_timeout_sec=float(_attach_ui_heal_ensure_subprocess_sec()),
        )
        _ATTACH_CLIENT_WARMUP_URLS.clear()
    except ImportError:
        pass


def _attach_client_warmup_timeout_sec() -> float:
    """Budget for one client hydration warmup.

    A cold client bundle has to be compiled by the dev server before the page can boot, and a busy
    host makes that compile take minutes (a single chunk was measured at 190s). The budget therefore
    scales with the same host-load ratio the other E2E budgets use, instead of a fixed 30s that
    silently expires while the compile is still running.
    """
    base = 30.0 if _parallel_chrome_e2e_active() else 90.0
    try:
        from dev_gate.contract import host_load_ratio

        ratio = max(0.0, float(host_load_ratio()))
    except (ImportError, OSError, AttributeError, RuntimeError, ValueError):
        ratio = 0.0
    if ratio <= 0.0:
        return base
    # Load per core 1.0 already means "twice as loaded as one core can serve"; scale linearly and cap.
    return min(300.0, base * max(1.0, ratio))


def _trigger_attach_client_warmup_once(*, page_url: str | None = None) -> None:
    """Run global CDP client hydration once when attach ADMIT skipped clientHot (body SSOT).

    A failed warmup does not mark the URL as warmed: the client is still cold, and the next caller has
    to be able to try again (the compile may simply have needed more time).
    """

    global _ATTACH_CLIENT_WARMUP_URLS
    ui = (page_url or f"{get_e2e_ui_url().rstrip('/')}/").rstrip("/") + "/"
    if ui in _ATTACH_CLIENT_WARMUP_URLS:
        return
    monorepo_root = Path(__file__).resolve().parents[5]
    warmup_py = monorepo_root / "myrm-agent/scripts/dev/lib/browser_orchestrator/frontend_client_warmup.py"
    if not warmup_py.is_file():
        return
    server_root = Path(__file__).resolve().parents[2]
    venv_py = server_root / ".venv/bin/python"
    py = str(venv_py) if venv_py.is_file() else sys.executable
    cdp_port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
    touch_wall_progress(current_node="attach_client_warmup")
    cli_timeout_sec = _attach_client_warmup_timeout_sec()
    try:
        completed = subprocess.run(
            [
                py,
                str(warmup_py),
                "--cdp-port",
                str(cdp_port),
                "--url",
                ui,
                "--timeout-sec",
                str(cli_timeout_sec),
            ],
            timeout=float(cli_timeout_sec + 10),
            check=False,
            capture_output=True,
            cwd=str(server_root),
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if completed.returncode == 0:
        _ATTACH_CLIENT_WARMUP_URLS.add(ui)
        print(
            f"E2E_CLIENT_WARMUP_OK: url={ui} budget={cli_timeout_sec:.0f}s",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            f"E2E_CLIENT_WARMUP_FAILED: url={ui} rc={completed.returncode} budget={cli_timeout_sec:.0f}s",
            file=sys.stderr,
            flush=True,
        )
