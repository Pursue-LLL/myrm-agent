"""Shared scripts and observations for Chrome chat UI E2E."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

_E2E_RUNTIME_BINDING_PREFIX = "myrm-e2e-v1:"
_E2E_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


def _normalize_loopback_http_origin(origin: str, *, env_name: str) -> str:
    trimmed = origin.strip().rstrip("/")
    if not trimmed:
        raise RuntimeError(f"{env_name} is empty")
    parsed = urlsplit(trimmed)
    hostname = (parsed.hostname or "").strip().lower()
    if (
        parsed.scheme not in {"http", "https"}
        or hostname not in _LOOPBACK_HOSTS
        or bool(parsed.username)
        or bool(parsed.password)
        or bool(parsed.query)
        or bool(parsed.fragment)
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeError(
            f"{env_name} must be an explicit loopback HTTP origin (127.0.0.1 / localhost / ::1 / 0.0.0.0): {trimmed}"
        )
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _validate_loopback_http_url(url: str) -> None:
    parsed = urlsplit(url.strip())
    hostname = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or hostname not in _LOOPBACK_HOSTS:
        raise RuntimeError(f"E2E HTTP helper only permits loopback URLs: {url}")


def get_e2e_api_url() -> str:
    return _normalize_loopback_http_origin(
        os.getenv("E2E_API_BASE", "http://127.0.0.1:8080"),
        env_name="E2E_API_BASE",
    )


def create_e2e_chat_via_api(chat_id: str, *, api_url: str | None = None) -> None:
    """Create a chat session on the active E2E API base (signoff clarify API leg)."""
    resolved = resolve_e2e_api_base(api_url or get_e2e_api_url())
    if not resolved:
        raise RuntimeError("E2E_API_BASE missing for create_e2e_chat_via_api")
    url = f"{resolved.rstrip('/')}/api/v1/chats/"
    timeout_sec = signoff_parallel_force_chat_timeout_sec(15.0)
    _e2e_api_post_json(url, {"chat_id": chat_id}, timeout_sec=timeout_sec)


def cancel_e2e_chat_agent_via_api(chat_id: str, *, api_url: str | None = None) -> bool:
    """Cancel in-flight agent-stream on chat_id (releases AgentBusy session for retry)."""
    resolved = resolve_e2e_api_base(api_url or get_e2e_api_url())
    if not resolved:
        return False
    url = f"{resolved.rstrip('/')}/api/v1/agents/chats/{chat_id}/cancel"
    try:
        result = _e2e_api_post_json(url, {}, timeout_sec=10.0, max_attempts=1)
    except (TimeoutError, OSError, urllib.error.URLError, urllib.error.HTTPError):
        return False
    if isinstance(result, dict):
        data = result.get("data")
        if isinstance(data, dict) and data.get("cancelled") is True:
            return True
    return False


def shpoib_parallel_shell_timeout_sec(timeout_sec: float) -> float:
    """Shell hydration budget for parallel SHPOIB chrome_e2e on shared :3000.

    R73-A: cap at bootstrap wall — never 420s outer deadline that
    defeats SHELL_PROBE_STALL_FAIL_FAST_SEC skeleton fail-fast.
    R220: signoff parallel uses pessimistic bootstrap cap (not 180s mux-undercount).
    """
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return timeout_sec
    signoff = os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    active_leases = 0
    try:
        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except Exception:
        active_leases = 0
    pessimistic = signoff and active_leases >= 2
    try:
        from transport_supervisor import bootstrap_wall_cap_sec

        bootstrap_cap = float(bootstrap_wall_cap_sec(pessimistic=pessimistic))
    except ImportError:
        from dev_gate_contract import E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV

        bootstrap_cap = float(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV)
    base_floor = max(timeout_sec, 120.0)
    scaled = max(base_floor, 120.0 + active_leases * 15.0)
    return min(scaled, bootstrap_cap)


def signoff_parallel_force_chat_timeout_sec(base_sec: float) -> float:
    """Extend desktop signoff force-chat wall timeouts under parallel wave load."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base_sec
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except Exception:
        active_leases = 0
    try:
        from transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except Exception:
        parallel_tests = 0
        mux_peers = 0
    load = max(active_leases, parallel_tests, mux_peers)
    # Signoff always applies a parallel headroom floor (Run#11 showed 50s/35s base under load).
    floor = max(base_sec, 90.0 if base_sec >= 45.0 else 70.0)
    scaled = floor + load * 12.0
    cap = 420.0
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        try:
            from dev_gate_contract import SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC

            cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC)
        except ImportError:
            cap = 420.0
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in ("1", "true", "yes"):
        scaled += 60.0
        cap = max(cap, 480.0)
    return min(scaled, cap)


def e2e_parallel_config_api_timeout_sec(base_sec: float) -> float:
    """Scale omni-config API timeouts under parallel chrome_e2e load (Phase C ramp SSOT)."""
    active_leases = 0
    parallel_tests = 0
    try:
        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except Exception:
        active_leases = 0
    try:
        from transport_supervisor import parallel_active_test_count

        parallel_tests = parallel_active_test_count()
    except Exception:
        parallel_tests = 0
    load = max(active_leases, parallel_tests)
    if load <= 0:
        return base_sec
    floor = max(base_sec, 15.0)
    scaled = floor + load * 10.0
    return min(scaled, 120.0)


def signoff_parallel_desktop_wall_clock_fail_sec(base_sec: float = 280.0) -> float:
    """Extend desktop approval per-attempt wall under parallel desktop soak (R211/R213)."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base_sec
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() not in ("1", "true", "yes"):
        return base_sec
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except Exception:
        active_leases = 0
    try:
        from transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except Exception:
        parallel_tests = 0
        mux_peers = 0
    load = max(active_leases, parallel_tests, mux_peers)
    floor = max(base_sec, 280.0)
    scaled = floor + load * 35.0
    return min(scaled, 600.0)


def signoff_parallel_desktop_progress_api_wall_sec(base_sec: float = 15.0) -> float:
    """Extend desktop progress API poll wall under parallel desktop soak (R212)."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base_sec
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() not in ("1", "true", "yes"):
        return base_sec
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except Exception:
        active_leases = 0
    try:
        from transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except Exception:
        parallel_tests = 0
        mux_peers = 0
    load = max(active_leases, parallel_tests, mux_peers)
    floor = max(base_sec, 15.0)
    scaled = floor + load * 4.0
    return min(scaled, 45.0)


def shpoib_shell_wait_slice_cap(remaining_sec: float) -> float:
    """Per-iteration cap for MCP shell wait loops (parallel SHPOIB needs >60s)."""
    remaining_sec = max(0.0, remaining_sec)
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1":
        return max(60.0, min(remaining_sec, 180.0))
    return min(remaining_sec, 60.0)


def get_e2e_ui_url() -> str:
    return _normalize_loopback_http_origin(
        os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000"),
        env_name="E2E_UI_BASE",
    )


_OK_REPLY_RE = re.compile(r"(?:\bOK\b|GOAL_OK)", re.IGNORECASE)
_DONE_REPLY_RE = re.compile(r"\bDONE\b", re.IGNORECASE)
_AGENT_TURN_DONE_RE = re.compile(r"(?:\bOK\b|GOAL_OK|\bDONE\b)", re.IGNORECASE)
_CLARIFY_SKIP_DONE_RE = re.compile(
    r"DONE-SKIPPED|Clarification answered|已回答澄清",
    re.IGNORECASE,
)
_E2E_API_REQUEST_ATTEMPTS = 3
_E2E_API_REQUEST_BACKOFF_SEC = 2.0


def resolve_e2e_api_base(api_base: str | None = None) -> str:
    raw = (api_base or os.getenv("E2E_API_BASE", "")).strip()
    if not raw:
        return ""
    return _normalize_loopback_http_origin(raw, env_name="E2E_API_BASE")


def _e2e_api_urlopen(
    req: urllib.request.Request,
    *,
    timeout_sec: float,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> object:
    """Retry loopback E2E API reads on transient socket/timeouts under parallel load."""
    _validate_loopback_http_url(req.full_url)
    last_error: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return urllib.request.urlopen(req, timeout=timeout_sec)  # noqa: S310
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {409, 423, 500, 503} and attempt + 1 < max_attempts:
                time.sleep(_E2E_API_REQUEST_BACKOFF_SEC * (attempt + 1))
                continue
            raise
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 >= max_attempts:
                raise
            time.sleep(_E2E_API_REQUEST_BACKOFF_SEC * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("E2E API request failed without response")


def _set_http_response_read_timeout(resp: object, timeout_sec: float) -> None:
    """Apply a per-read socket timeout so SSE loops can honor wall deadlines."""
    fp = getattr(resp, "fp", None)
    if fp is None:
        return
    raw = getattr(fp, "raw", None)
    sock = getattr(raw, "_sock", None) if raw is not None else None
    if sock is not None:
        sock.settimeout(max(0.1, timeout_sec))


def _e2e_api_get_json(
    url: str,
    *,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> object:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json"}
    )  # noqa: S310 - validated in _e2e_api_urlopen
    with _e2e_api_urlopen(
        req, timeout_sec=timeout_sec, max_attempts=max_attempts
    ) as resp:
        return json.loads(resp.read())


def _e2e_api_post_json(
    url: str,
    body: dict[str, object],
    *,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> object:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _e2e_api_urlopen(
        req, timeout_sec=timeout_sec, max_attempts=max_attempts
    ) as resp:
        raw = resp.read()
        if not raw:
            return {}
        return json.loads(raw)


def e2e_runtime_binding(api_base: str | None = None) -> dict[str, object] | None:
    """Return a validated page-local private Backend binding."""
    base = resolve_e2e_api_base(api_base)
    runtime_id = os.getenv("MYRM_E2E_PRIVATE_RUNTIME_ID", "").strip()
    run_id = os.getenv("MYRM_E2E_RUN_ID", "").strip()
    ui_base = get_e2e_ui_url()
    if not base or not runtime_id or not run_id:
        return None
    if not _E2E_RUNTIME_ID_RE.fullmatch(runtime_id) or not _E2E_RUNTIME_ID_RE.fullmatch(
        run_id
    ):
        raise RuntimeError("E2E runtime/run identity contains unsupported characters")
    api = urlsplit(base)
    ui = urlsplit(ui_base)
    loopback_hosts = _LOOPBACK_HOSTS
    if (
        api.scheme not in {"http", "https"}
        or ui.scheme not in {"http", "https"}
        or api.hostname not in loopback_hosts
        or ui.hostname not in loopback_hosts
        or not api.port
        or not ui.port
    ):
        raise RuntimeError(
            "E2E runtime binding only permits explicit loopback HTTP origins"
        )
    return {
        "version": 1,
        "runId": run_id,
        "runtimeId": runtime_id,
        "apiBase": f"{api.scheme}://{api.hostname}:{api.port}",
        "uiOrigin": f"{ui.scheme}://{ui.hostname}:{ui.port}",
    }


def e2e_runtime_binding_source(api_base: str | None = None) -> str | None:
    binding = e2e_runtime_binding(api_base)
    if binding is None:
        return None
    name = _E2E_RUNTIME_BINDING_PREFIX + json.dumps(binding, separators=(",", ":"))
    return (
        f"window.name = {json.dumps(name)};"
        f"window.__MYRM_E2E_RUNTIME__ = Object.freeze({json.dumps(binding)});"
        f"window.__MYRM_E2E_API_BASE__ = {json.dumps(binding['apiBase'])};"
        f"window.__MYRM_E2E_DIRECT_SSE__ = true;"
    )


def e2e_runtime_bootstrap_apply_js(api_base: str | None = None) -> str | None:
    """Apply binding + health-ready promise after navigation (MCP mux path)."""
    binding = e2e_runtime_binding(api_base)
    if binding is None:
        return None
    binding_json = json.dumps(binding)
    prefix = json.dumps(_E2E_RUNTIME_BINDING_PREFIX)
    return f"""(async () => {{
  const binding = Object.freeze({binding_json});
  const prefix = {prefix};
  window.name = prefix + JSON.stringify(binding);
  window.__MYRM_E2E_RUNTIME__ = binding;
  window.__MYRM_E2E_API_BASE__ = binding.apiBase;
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const nativeFetch = window.fetch.bind(window);
  const healthUrl = `${{binding.apiBase}}/api/v1/health`;
  window.__MYRM_E2E_RUNTIME_READY__ = nativeFetch(healthUrl, {{ cache: 'no-store' }})
    .then(async (response) => {{
      if (!response.ok) {{
        throw new Error(`E2E_RUNTIME_HEALTH_HTTP_${{response.status}}`);
      }}
      const payload = await response.json();
      if (payload.runtime_id !== binding.runtimeId) {{
        throw new Error(
          `E2E_RUNTIME_MISMATCH expected=${{binding.runtimeId}} actual=${{payload.runtime_id || '<missing>'}}`,
        );
      }}
      window.dispatchEvent(new CustomEvent('myrm_e2e_runtime_ready', {{ detail: binding }}));
      return binding;
    }});
  try {{
    const value = await window.__MYRM_E2E_RUNTIME_READY__;
    return {{ ok: true, runtimeId: value.runtimeId, apiBase: value.apiBase }};
  }} catch (error) {{
    return {{ ok: false, error: String(error) }};
  }}
}})()"""


def e2e_api_base_persist_source(api_base: str | None = None) -> str | None:
    """JS source for Page.addScriptToEvaluateOnNewDocument (survives hard navigation)."""
    runtime_source = e2e_runtime_binding_source(api_base)
    if runtime_source is not None:
        return runtime_source
    base = resolve_e2e_api_base(api_base)
    if not base:
        return None
    encoded = json.dumps(base)
    return f"window.__MYRM_E2E_API_BASE__ = {encoded};"


def e2e_api_base_inject_js(api_base: str | None = None) -> str:
    runtime_source = e2e_runtime_binding_source(api_base)
    if runtime_source is not None:
        binding = e2e_runtime_binding(api_base)
        assert binding is not None
        return f"(() => {{{runtime_source} return {{ ok: true, base: {json.dumps(binding['apiBase'])}, runtimeId: {json.dumps(binding['runtimeId'])} }}; }})()"
    base = resolve_e2e_api_base(api_base)
    if not base:
        return "(() => ({ ok: false, err: 'no-api-base' }))()"
    encoded = json.dumps(base)
    return f"""(() => {{
  window.__MYRM_E2E_API_BASE__ = {encoded};
  return {{ ok: true, base: {encoded} }};
}})()"""


E2E_API_BINDING_PROBE_JS = """
(() => ({
  apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
  runtimeId: window.__MYRM_E2E_RUNTIME__?.runtimeId ?? null,
  directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
}))()
""".strip()


def require_e2e_api_binding_probe(
    probe: object,
    expected_api_base: str,
) -> dict[str, object]:
    """Fail closed when WebUI document is not bound to the expected SHPOIB private API."""
    if not isinstance(probe, dict):
        raise AssertionError(f"E2E API binding probe invalid: {probe!r}")
    expected = expected_api_base.rstrip("/")
    actual = str(probe.get("apiBase") or "").rstrip("/")
    if actual != expected:
        raise AssertionError(
            f"E2E API binding mismatch: expected {expected!r}, got {actual!r}; "
            f"probe={probe!r}"
        )
    return probe


PREPARE_AUTOMATION_SEND_JS = """
(() => {
  window.__MYRM_E2E_CHAT__?.prepareAutomationSend?.();
  return { ok: true };
})()
""".strip()

COUNT_DOM_USER_MESSAGES_JS = """
(() => {
  const main = document.querySelector('main');
  const assistantCount =
    main?.querySelectorAll('[data-test-id="assistant-message"]')?.length || 0;
  const allWithId = main?.querySelectorAll('[data-message-id]')?.length || 0;
  return Math.max(0, allWithId - assistantCount);
})()
""".strip()


def _api_provider_ready(*, api_url: str | None = None) -> bool:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/config/readiness",
            timeout_sec=5.0,
        )
    except Exception:
        return False
    provider = payload.get("provider") if isinstance(payload, dict) else None
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


def fetch_provider_readiness_snapshot() -> dict[str, object]:
    """Return private-pool provider readiness for E2E failure diagnostics."""
    api_base = get_e2e_api_url()
    try:
        payload = _e2e_api_get_json(
            f"{api_base}/api/v1/config/readiness",
            timeout_sec=5.0,
        )
    except Exception as exc:
        return {"apiBase": api_base, "error": str(exc)}
    if not isinstance(payload, dict):
        return {"apiBase": api_base, "error": "invalid_readiness_payload"}
    provider = payload.get("provider")
    return {
        "apiBase": api_base,
        "provider": provider if isinstance(provider, dict) else None,
        "degraded": payload.get("degraded"),
    }


def wait_e2e_provider_ready(
    *,
    api_url: str | None = None,
    timeout_sec: float = 60.0,
    poll_interval_sec: float = 1.0,
) -> bool:
    """Poll private-pool health + provider readiness (SHPOIB bootstrap race)."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    timeout_sec = e2e_parallel_config_api_timeout_sec(timeout_sec)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        health_ok = False
        try:
            health_payload = _e2e_api_get_json(
                f"{resolved_api}/api/v1/health",
                timeout_sec=5.0,
            )
            health_ok = (
                isinstance(health_payload, dict)
                and health_payload.get("status") == "healthy"
            )
        except Exception:
            health_ok = False
        if health_ok and _api_provider_ready(api_url=resolved_api):
            return True
        time.sleep(poll_interval_sec)
    return False


def fetch_e2e_goal_status(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, object] | None:
    """Return the active goal dict for a chat session, or None if not yet persisted."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/goals/{chat_id}/status",
            timeout_sec=15.0,
        )
    except Exception:
        return None
    goal = payload.get("goal")
    return goal if isinstance(goal, dict) else None


def wait_e2e_goal_status(
    chat_id: str,
    *,
    timeout_sec: float = 90.0,
    poll_interval_sec: float = 1.0,
    api_url: str | None = None,
) -> dict[str, object] | None:
    """Poll private-backend goal persistence (orchestrator may lag turn completion)."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        goal = fetch_e2e_goal_status(chat_id, api_url=api_url)
        if goal is not None:
            return goal
        time.sleep(poll_interval_sec)
    return None


def ensure_e2e_goal_active(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, object]:
    """Normalize API goal to ACTIVE for B/D UI flows; fail fast on terminal states."""
    goal = fetch_e2e_goal_status(chat_id, api_url=api_url)
    if goal is None:
        return {"ok": False, "err": "no-goal"}

    status = str(goal.get("status") or "")
    if status in {"complete", "cancelled"}:
        return {
            "ok": False,
            "err": f"terminal-{status}",
            "status": status,
        }

    if status == "wait":
        unwait = post_goal_status_action(chat_id, "unwait", api_url=api_url)
        if unwait.get("new_status") != "active":
            return {"ok": False, "err": "unwait-failed", "payload": unwait}
        status = "active"

    if status in {"paused", "budget_limited", "needs_human_review", "pending_approval"}:
        resume = post_goal_status_action(chat_id, "resume", api_url=api_url)
        if resume.get("new_status") != "active":
            return {
                "ok": False,
                "err": "resume-failed",
                "payload": resume,
                "prior_status": status,
            }
        status = "active"

    if status != "active":
        return {"ok": False, "err": f"unexpected-status-{status}", "status": status}

    return {"ok": True, "status": "active"}


def post_goal_status_action(
    chat_id: str,
    action: str,
    *,
    api_url: str | None = None,
    note: str | None = None,
    wait_reason: str | None = None,
) -> dict[str, object]:
    """POST /api/v1/goals/{chat_id}/status for E2E setup/teardown."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    body: dict[str, object] = {"action": action}
    if note is not None:
        body["note"] = note
    if wait_reason is not None:
        body["wait_reason"] = wait_reason
    try:
        payload = _e2e_api_post_json(
            f"{resolved_api}/api/v1/goals/{chat_id}/status",
            body,
            timeout_sec=15.0,
        )
        return payload if isinstance(payload, dict) else {"value": payload}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


_CHAT_ID_PATH_RE = re.compile(
    r"^/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|c-[a-z0-9\-]+)$",
    re.IGNORECASE,
)

PAGE_PROBE_JS = """
(() => {
  const input = document.querySelector('[data-chat-input]');
  const skeleton = !!document.querySelector('[aria-label="Loading messages"]');
  const fiberKey = input
    ? Object.keys(input).find((k) => k.startsWith('__reactFiber$'))
    : null;
  return {
    hasInput: !!input,
    clientHydrated: !!fiberKey || !!(window.__MYRM_E2E_CHAT__?.setInputMessage),
    hasBridge: !!window.__MYRM_E2E_CHAT__,
    skeleton,
    hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
    path: location.pathname,
  };
})()
""".strip()

RESET_CHAT_JS = """
(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (bridge?.resetChat) {
    bridge.resetChat();
    return { ok: true, mode: 'bridge-reset' };
  }
  if (document.querySelector('[data-chat-input]')) {
    return { ok: true, mode: 'already' };
  }
  const newBtn = Array.from(document.querySelectorAll('aside button')).find((b) => {
    const text = (b.textContent || '').trim();
    return text.includes('新对话') || text.includes('New chat');
  });
  if (newBtn) {
    newBtn.click();
    return { ok: true, mode: 'new-chat' };
  }
  return { ok: false, mode: 'no-button' };
})()
""".strip()

MODEL_PROBE_JS = """
(() => {
  const trigger = document.querySelector('[data-testid="model-picker-trigger"]');
  const label = (trigger?.innerText || '').trim();
  const unconfigured = /未配置|Not configured|Select model/i.test(label);
  const sendBtn = document.querySelector('.message-send-btn');
  return {
    ok: !unconfigured && label.length > 0,
    label,
    unconfigured,
    sendDisabled: !!sendBtn?.disabled,
  };
})()
""".strip()

SELECT_MIMO_MODEL_JS = """
(() => {
  const trigger = document.querySelector('[data-testid="model-picker-trigger"]');
  if (!trigger) return { ok: false, err: 'no model trigger' };
  const label = (trigger.innerText || '').trim();
  if (/mimo-v2/i.test(label) && !/未配置|Not configured|Select model/i.test(label)) {
    return { ok: true, mode: 'already-mimo', label };
  }
  trigger.click();
  const pick = () => {
    const popover = document.querySelector('[data-radix-popper-content-wrapper]');
    const scope = popover || document;
    const nodes = Array.from(scope.querySelectorAll('button, [role="option"]'));
    const target = nodes.find((el) => /mimo-v2\\.5-pro/i.test((el.textContent || '').trim()));
    if (target) {
      target.click();
      return { ok: true, mode: 'picked-mimo', label: (target.textContent || '').trim().slice(0, 80) };
    }
    return null;
  };
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      const first = pick();
      if (first) {
        resolve(first);
        return;
      }
      setTimeout(() => resolve(pick() || { ok: false, err: 'mimo option not found' }), 600);
    });
  });
})()
""".strip()

SELECT_FIRST_ENABLED_MODEL_JS = """
(() => {
  const trigger = document.querySelector('[data-testid="model-picker-trigger"]');
  if (!trigger) return { ok: false, err: 'no model trigger' };
  const label = (trigger.innerText || '').trim();
  if (!/未配置|Not configured|Select model/i.test(label) && label.length > 0) {
    return { ok: true, mode: 'already', label };
  }
  trigger.click();
  const pick = () => {
    const popover = document.querySelector('[data-radix-popper-content-wrapper]');
    const scope = popover || document;
    const slotTabs = new Set(['主模型', 'Primary', '备用', 'Fallback', 'Safety']);
    const buttons = Array.from(scope.querySelectorAll('button'));
    const modelBtn = buttons.find((el) => {
      const text = (el.textContent || '').trim();
      if (!text || text.length > 80) return false;
      if (slotTabs.has(text)) return false;
      if (/未配置|Not configured|搜索|Search|no enabled|no matching/i.test(text)) return false;
      if (el.closest('[data-testid="model-picker-trigger"]')) return false;
      const row = el.closest('.max-h-80');
      return !!row || (!!popover && popover.contains(el) && el.classList.contains('cursor-pointer'));
    });
    if (modelBtn) {
      modelBtn.click();
      return {
        ok: true,
        mode: 'picked',
        label: (modelBtn.textContent || '').trim().slice(0, 80),
      };
    }
    return null;
  };
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      const first = pick();
      if (first) {
        resolve(first);
        return;
      }
      setTimeout(() => resolve(pick() || { ok: false, err: 'enabled model option not found' }), 600);
    });
  });
})()
""".strip()

DISMISS_MODALS_JS = """
(() => {
  const host = location.hostname;
  if (host !== '127.0.0.1' && host !== 'localhost') {
    return { ok: false, err: 'not-localhost', href: location.href };
  }
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
    localStorage.setItem('myrm_onboarding_complete', 'true');
  } catch (err) {
    return { ok: false, err: String(err), href: location.href };
  }
  Array.from(document.querySelectorAll('button')).forEach((b) => {
    const text = (b.textContent || '').trim();
    if (/稍后再说|Later|Skip for now|关闭|Dismiss|Not now|跳过|Skip/i.test(text)) {
      b.click();
    }
  });
  return { ok: true };
})()
""".strip()

E2E_BRIDGE_INSTALL_JS = """
(() => {
  const host = location.hostname;
  if (host !== '127.0.0.1' && host !== 'localhost') {
    return { ok: false, err: 'not-localhost' };
  }
  const syncInput = (message) => {
    const input = document.querySelector('[data-chat-input]');
    if (!input) return false;
    const text = String(message);
    const applyOnChange = (onChange) => {
      const tracker = input._valueTracker;
      if (tracker) tracker.setValue('');
      input.value = text;
      onChange({ target: input, currentTarget: input });
    };
    const propsKey = Object.keys(input).find((k) => k.startsWith('__reactProps$'));
    if (propsKey && input[propsKey]?.onChange) {
      applyOnChange(input[propsKey].onChange);
      return true;
    }
    const fiberKey = Object.keys(input).find((k) => k.startsWith('__reactFiber$'));
    if (fiberKey) {
      let fiber = input[fiberKey];
      while (fiber) {
        const onChange = fiber.memoizedProps?.onChange;
        if (typeof onChange === 'function') {
          applyOnChange(onChange);
          return true;
        }
        fiber = fiber.return;
      }
    }
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
    if (setter) setter.call(input, text);
    else input.value = text;
    input.dispatchEvent(new InputEvent('input', { bubbles: true, data: text, inputType: 'insertText' }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };
  const install = () => {
    const existing = window.__MYRM_E2E_CHAT__;
    if (
      existing?.pinLiteModelForE2e
      || existing?.pinBasicModelForE2e
      || (existing?.setInputMessage && existing?.handleSubmit && !existing.__e2eFallback)
    ) {
      return { ok: true, mode: 'react-bridge' };
    }
    window.__MYRM_E2E_CHAT__ = {
      __e2eFallback: true,
      setInputMessage: (message) => { syncInput(message); },
      handleSubmit: () => {
        const btn = document.querySelector('.message-send-btn');
        if (!btn) return;
        const fiberKey = Object.keys(btn).find((k) => k.startsWith('__reactFiber$'));
        if (fiberKey) {
          let fiber = btn[fiberKey];
          while (fiber) {
            const onClick = fiber.memoizedProps?.onClick;
            if (typeof onClick === 'function') {
              onClick({ preventDefault() {}, stopPropagation() {} });
              return;
            }
            fiber = fiber.return;
          }
        }
        const propsKey = Object.keys(btn).find((k) => k.startsWith('__reactProps$'));
        if (propsKey && btn[propsKey]?.onClick) {
          btn[propsKey].onClick({ preventDefault() {}, stopPropagation() {} });
          return;
        }
        if (!btn.disabled) btn.click();
      },
      getInputMessage: () => {
        const input = document.querySelector('[data-chat-input]');
        return (input?.value || '').trim();
      },
    };
    return { ok: true, mode: 'installed-fallback' };
  };
  if (window.__MYRM_E2E_CHAT__?.setInputMessage && window.__MYRM_E2E_CHAT__?.handleSubmit) {
    if (!window.__MYRM_E2E_CHAT__.__e2eFallback) {
      return { ok: true, mode: 'existing-react' };
    }
    return { ok: true, mode: 'existing-fallback' };
  }
  return install();
})()
""".strip()


def chat_id_from_path(path: str) -> str | None:
    match = _CHAT_ID_PATH_RE.match(path.strip())
    return match.group(1) if match else None


def warmup_frontend(base_url: str, *, timeout_sec: float = 120.0) -> None:
    """Warm Next.js dev compile before CDP navigation (avoids hung first paint)."""
    deadline = time.monotonic() + timeout_sec
    last_error = "unknown"
    while time.monotonic() < deadline:
        try:
            warm_url = base_url.rstrip("/") + "/"
            _validate_loopback_http_url(warm_url)
            with urllib.request.urlopen(
                warm_url, timeout=45
            ) as resp:  # noqa: S310 - explicit loopback validation above
                if resp.status == 200:
                    return
                last_error = f"HTTP {resp.status}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(3)
    raise TimeoutError(
        f"Frontend warmup failed within {timeout_sec:.0f}s: {last_error}"
    )


def fetch_chat_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> list[dict[str, object]]:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    req = urllib.request.Request(  # noqa: S310 - validated in _e2e_api_urlopen
        f"{resolved_api}/api/v1/chats/{chat_id}/messages",
        headers={"Accept": "application/json"},
    )
    try:
        with _e2e_api_urlopen(
            req, timeout_sec=timeout_sec, max_attempts=max_attempts
        ) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    messages = data.get("messages")
    return messages if isinstance(messages, list) else []


FILE_WRITE_TOOL_E2E_NAME = "file_write_tool"
EMPTY_FILE_WRITE_ERROR = "Cannot write empty file content"


def _structured_tool_name(call: dict[str, object]) -> str:
    fn = call.get("function")
    return str(
        call.get("name") or (fn.get("name") if isinstance(fn, dict) else "") or ""
    )


def file_write_tool_call_count(
    chat_id: str,
    *,
    api_url: str | None = None,
    tool_name: str = FILE_WRITE_TOOL_E2E_NAME,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> int:
    count = 0
    for msg in fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    ):
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if isinstance(call, dict) and _structured_tool_name(call) == tool_name:
                    count += 1
        if str(msg.get("role") or "") == "tool":
            name = str(msg.get("name") or msg.get("tool_name") or "")
            if name == tool_name:
                count += 1
    return count


def file_write_tool_invoked_in_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
    tool_name: str = FILE_WRITE_TOOL_E2E_NAME,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> bool:
    """SSOT: real tool invoke from assistant/tool messages — never user prompt text."""
    return (
        file_write_tool_call_count(
            chat_id,
            api_url=api_url,
            tool_name=tool_name,
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
        )
        >= 1
    )


def empty_write_failure_in_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
    tool_name: str = FILE_WRITE_TOOL_E2E_NAME,
    empty_error: str = EMPTY_FILE_WRITE_ERROR,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> tuple[bool, bool]:
    tool_invoked = file_write_tool_invoked_in_messages(
        chat_id,
        api_url=api_url,
        tool_name=tool_name,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    has_mutation_failure = False
    for msg in fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    ):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        blob = json.dumps(msg, ensure_ascii=False, default=str)
        failures = msg.get("fileMutationFailures")
        if not isinstance(failures, list):
            meta = msg.get("metadata")
            if isinstance(meta, dict):
                failures = meta.get("fileMutationFailures")
                steps = meta.get("progressSteps")
                if isinstance(steps, list):
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        if step.get("type") == "file_mutation_failed":
                            has_mutation_failure = True
                        detail = json.dumps(step, ensure_ascii=False, default=str)
                        if empty_error in detail:
                            has_mutation_failure = True
        if isinstance(failures, list) and failures:
            for row in failures:
                if not isinstance(row, dict):
                    continue
                preview = str(row.get("error_preview") or "")
                if empty_error in preview:
                    has_mutation_failure = True
        if role != "user" and empty_error in blob:
            has_mutation_failure = True
    return tool_invoked, has_mutation_failure


def steer_chat_message(
    chat_id: str,
    message: str,
    *,
    api_url: str | None = None,
) -> dict[str, object]:
    """Steer an in-flight agent turn via REST (no Chrome UI surface required)."""
    normalized_chat = chat_id.strip()
    normalized_message = message.strip()
    if not normalized_chat or not normalized_message:
        return {"ok": False, "err": "missing-chat-id-or-message"}
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    payload = _e2e_api_post_json(
        f"{resolved_api}/api/v1/agents/chats/{normalized_chat}/steer",
        {"message": normalized_message},
        timeout_sec=30.0,
    )
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict) and data.get("steered") is True:
            return {"ok": True, "mode": "steerApi", "chatId": normalized_chat}
        if payload.get("success") is True:
            return {"ok": True, "mode": "steerApi", "chatId": normalized_chat}
    return {"ok": False, "err": "steer-api-rejected", "payload": payload}


def nudge_agent_stream_turn(
    chat_id: str,
    agent_id: str,
    message: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    """Follow-up turn via agent-stream REST (no Chrome bridge; R137 LIVE empty-write nudge)."""
    normalized_chat = chat_id.strip()
    normalized_agent = agent_id.strip()
    normalized_message = message.strip()
    if not normalized_chat or not normalized_agent or not normalized_message:
        return {"ok": False, "err": "missing-chat-agent-or-message"}
    payload: dict[str, object] = {
        "messageId": f"e2e-nudge-{uuid.uuid4().hex[:10]}",
        "chatId": normalized_chat,
        "query": normalized_message,
        "actionMode": "agent",
        "agentId": normalized_agent,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    result = _collect_agent_stream_events(
        payload,
        api_url=api_url,
        timeout_sec=timeout_sec,
    )
    error = result.get("error")
    if isinstance(error, dict):
        return {
            "ok": False,
            "mode": "agentStreamNudge",
            "error": error,
            "events": result.get("events"),
        }
    return {"ok": True, "mode": "agentStreamNudge", "events": result.get("events", [])}


def chat_browser_gate_from_api(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
) -> dict[str, object]:
    """REST mirror of E2E ``getBrowserToolProgress`` when MUX probes are degraded."""
    normalized = chat_id.strip()
    if not normalized:
        return {"lastTool": "", "takeoverPending": False, "fromApi": True}
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    last_tool = ""
    messages = fetch_chat_messages(
        normalized, api_url=resolved_api, timeout_sec=timeout_sec
    )
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        steps = msg.get("progressSteps") or msg.get("progress_steps") or []
        if not isinstance(steps, list):
            continue
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool_name") or step.get("toolName") or "")
            if tool_name.startswith("browser_"):
                last_tool = tool_name
                break
        if last_tool:
            break
    takeover_pending = last_tool.endswith("browser_ask_human_tool")
    if not takeover_pending:
        try:
            payload = _e2e_api_get_json(
                f"{resolved_api}/api/v1/approvals?limit=50&offset=0",
                timeout_sec=10.0,
            )
            records = payload.get("approvals") if isinstance(payload, dict) else None
            if isinstance(records, list):
                for raw in records:
                    if not isinstance(raw, dict):
                        continue
                    if (
                        raw.get("action_type") == "browser_takeover"
                        and raw.get("status") == "PENDING"
                        and str(raw.get("chat_id") or "") == normalized
                    ):
                        takeover_pending = True
                        if not last_tool:
                            last_tool = "browser_ask_human_tool"
                        break
        except Exception:
            pass
    return {
        "lastTool": last_tool,
        "takeoverPending": takeover_pending,
        "fromApi": True,
    }


def fetch_pending_browser_takeover_resume(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, str] | None:
    """Return chat/message ids for a pending browser_takeover approval (REST-only)."""
    normalized = chat_id.strip()
    if not normalized:
        return None
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/approvals?limit=50&offset=0",
            timeout_sec=15.0,
        )
    except Exception:
        return None
    records = payload.get("approvals") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return None
    for raw in records:
        if not isinstance(raw, dict):
            continue
        if (
            raw.get("action_type") != "browser_takeover"
            or raw.get("status") != "PENDING"
            or str(raw.get("chat_id") or "") != normalized
        ):
            continue
        nested = raw.get("payload")
        message_id = ""
        if isinstance(nested, dict):
            message_id = str(
                nested.get("messageId") or nested.get("message_id") or ""
            ).strip()
        if not message_id:
            message_id = str(raw.get("message_id") or "").strip()
        if message_id:
            return {"chatId": normalized, "resumeMessageId": message_id}
    return None


def _resume_message_id_from_chat_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> str | None:
    """Resolve HITL resume messageId from persisted chat messages (yolo / no approval row)."""
    normalized = chat_id.strip()
    if not normalized:
        return None
    messages = fetch_chat_messages(normalized, api_url=api_url)
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        steps: object = msg.get("progressSteps") or msg.get("progress_steps")
        if not isinstance(steps, list):
            meta = msg.get("metadata")
            if isinstance(meta, dict):
                steps = meta.get("progressSteps") or meta.get("progress_steps")
        has_takeover = False
        if isinstance(steps, list):
            for step in reversed(steps):
                if not isinstance(step, dict):
                    continue
                tool_name = str(step.get("tool_name") or step.get("toolName") or "")
                if not tool_name.endswith("browser_ask_human_tool"):
                    continue
                has_takeover = True
                step_mid = str(
                    step.get("messageId") or step.get("message_id") or ""
                ).strip()
                if step_mid:
                    return step_mid
                break
        if has_takeover or msg.get("loading") is True:
            message_id = str(
                msg.get("messageId") or msg.get("message_id") or msg.get("id") or ""
            ).strip()
            if message_id:
                return message_id
    return None


def fetch_browser_takeover_resume_ids(
    chat_id: str,
    *,
    api_url: str | None = None,
) -> dict[str, str] | None:
    """Return chat/message ids for browser takeover resume (approvals → chat messages)."""
    normalized = chat_id.strip()
    if not normalized:
        return None
    ids = fetch_pending_browser_takeover_resume(normalized, api_url=api_url)
    if ids:
        return ids
    message_id = _resume_message_id_from_chat_messages(normalized, api_url=api_url)
    if message_id:
        return {"chatId": normalized, "resumeMessageId": message_id}
    return None


def chat_user_message_count(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> int:
    messages = fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    return sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )


def chat_messages_have_ok(
    chat_id: str,
    *,
    min_user_count: int = 1,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> bool:
    messages = fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    user_count = sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )
    if user_count < min_user_count:
        return False
    last_assistant: dict[str, object] | None = None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            last_assistant = msg
    if last_assistant is None:
        return False
    content = str(last_assistant.get("content") or "")
    return bool(_AGENT_TURN_DONE_RE.search(content))


def _config_http_json(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
    *,
    api_url: str | None = None,
    timeout_sec: float = 10.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> dict[str, object]:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(  # noqa: S310
        f"{resolved_api}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    with _e2e_api_urlopen(
        req, timeout_sec=timeout_sec, max_attempts=max_attempts
    ) as resp:  # noqa: S310
        raw = resp.read()
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"value": payload}


def fetch_config_value(
    config_key: str, *, api_url: str | None = None
) -> dict[str, object]:
    base_timeout = 15.0 if os.environ.get("E2E_SIGNOFF", "").strip() == "1" else 10.0
    timeout_sec = e2e_parallel_config_api_timeout_sec(base_timeout)
    attempts = _E2E_API_REQUEST_ATTEMPTS
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        # R221: mux gen bump / parallel SHPOIB may transiently stall config GET.
        attempts = max(attempts, 6)
    elif timeout_sec > base_timeout:
        attempts = max(attempts, 5)
    payload = _config_http_json(
        "GET",
        f"/api/v1/config/{config_key}",
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=attempts,
    )
    value = payload.get("value")
    return value if isinstance(value, dict) else {}


def put_config_value(
    config_key: str,
    value: dict[str, object],
    *,
    api_url: str | None = None,
) -> None:
    # PUT may block under parallel chrome_e2e on shared :8080 — longer timeout + retries.
    _config_http_json(
        "PUT",
        f"/api/v1/config/{config_key}",
        {"deviceId": "web", "value": value},
        api_url=api_url,
        timeout_sec=30.0,
        max_attempts=5,
    )


def wait_e2e_backend_ready(
    *,
    timeout_sec: float = 60.0,
    poll_interval_sec: float = 1.0,
    api_url: str | None = None,
) -> bool:
    """Poll private-backend /health until stack is accepting requests."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            payload = _e2e_api_get_json(
                f"{resolved_api}/api/v1/health",
                timeout_sec=5.0,
            )
            if isinstance(payload, dict) and payload.get("status") == "healthy":
                return True
        except Exception:
            pass
        time.sleep(poll_interval_sec)
    return False


def wait_e2e_cdp_ready(
    *,
    timeout_sec: float = 30.0,
    poll_interval_sec: float = 1.0,
    port: int | None = None,
) -> bool:
    """Poll Myrm E2E Chrome CDP (:9333) until attach endpoint responds."""
    resolved_port = port
    if resolved_port is None:
        raw = os.getenv("MYRM_CHROME_E2E_PORT", "9333").strip()
        try:
            resolved_port = int(raw)
        except ValueError:
            resolved_port = 9333
    endpoint = f"http://127.0.0.1:{resolved_port}/json/version"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(endpoint, timeout=3)  # noqa: S310
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(poll_interval_sec)
    return False


_SHARED_HOT_E2E_API_BASE = "http://127.0.0.1:8080"


def shared_hot_e2e_api_base() -> str:
    """Shared dev-stack API (:8080). Never the SHPOIB-monkeypatched ``E2E_API_BASE``."""
    explicit = os.getenv("MYRM_SHARED_E2E_API_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return _SHARED_HOT_E2E_API_BASE


def ensure_e2e_yolo_mode(*, api_url: str | None = None) -> None:
    """Enable YOLO mode for live Chrome agent E2E (skips tool approval gate)."""
    last_exc: BaseException | None = None
    current: dict[str, object] = {}
    for attempt in range(5):
        try:
            current = fetch_config_value("securityConfig", api_url=api_url)
            last_exc = None
            break
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_exc = exc
            if attempt >= 4:
                raise RuntimeError(
                    f"SHPOIB config fetch failed after 5 attempts: {exc}"
                ) from exc
            time.sleep(2.0 * (attempt + 1))
    if last_exc is not None:
        raise RuntimeError(f"SHPOIB config fetch failed: {last_exc}") from last_exc
    now = int(time.time())
    merged: dict[str, object] = {
        **current,
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": now,
        "yolo_mode_enabled": True,
        "yolo_mode_enabled_at": float(now),
        "yolo_mode_timeout": None,
        "permissions": {"*": "allow"},
        "domainHitlEnabled": False,
        "autoReviewEnabled": False,
        "planConfirmEnabled": False,
        "approvalTimeoutSeconds": 900,
        "approval_timeout_seconds": 900,
    }
    put_config_value("securityConfig", merged, api_url=api_url)
    persisted = fetch_config_value("securityConfig", api_url=api_url)
    if not persisted.get("yoloModeEnabled") and not persisted.get("yolo_mode_enabled"):
        raise RuntimeError(f"Failed to persist YOLO securityConfig: {persisted}")


def _hitl_security_payload(current: dict[str, object]) -> dict[str, object]:
    return {
        **current,
        "yoloModeEnabled": False,
        "yoloModeEnabledAt": None,
        "yoloModeTimeout": None,
        "yolo_mode_enabled": False,
        "yolo_mode_enabled_at": None,
        "yolo_mode_timeout": None,
        "autoModeEnabled": False,
        "autoReviewEnabled": False,
        "planConfirmEnabled": False,
        "domainHitlEnabled": False,
        "approvalTimeoutBehavior": "deny",
        "permissions": {
            "shell_exec": "ask",
            "code_interpreter": "ask",
            "computer_use": "ask",
        },
    }


def _pin_hitl_on_api(api_url: str, *, request_timeout_sec: float = 15.0) -> None:
    current_payload = _config_http_json(
        "GET",
        "/api/v1/config/securityConfig",
        api_url=api_url,
        timeout_sec=request_timeout_sec,
        max_attempts=5,
    )
    current_value = current_payload.get("value")
    current = current_value if isinstance(current_value, dict) else {}
    put_config_value(
        "securityConfig",
        _hitl_security_payload(current),
        api_url=api_url,
    )
    reset_url = (
        f"{api_url.rstrip('/')}/api/v1/security/allowlist/test/reset-hitl-runtime"
    )
    reset_req = urllib.request.Request(  # noqa: S310 - loopback validated below
        reset_url,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    _validate_loopback_http_url(reset_url)
    try:
        with _e2e_api_urlopen(
            reset_req, timeout_sec=request_timeout_sec, max_attempts=5
        ) as reset_resp:
            if reset_resp.status != 200:
                body = reset_resp.read(500)
                raise RuntimeError(
                    f"reset-hitl-runtime failed on {api_url}: {reset_resp.status} {body!r}"
                )
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    persisted_payload = _config_http_json(
        "GET",
        "/api/v1/config/securityConfig",
        api_url=api_url,
        timeout_sec=request_timeout_sec,
        max_attempts=5,
    )
    persisted_value = persisted_payload.get("value")
    persisted = persisted_value if isinstance(persisted_value, dict) else {}
    if persisted.get("yoloModeEnabled") or persisted.get("yolo_mode_enabled"):
        raise RuntimeError(
            f"Failed to disable YOLO securityConfig on {api_url}: {persisted}"
        )
    perms = persisted.get("permissions")
    if isinstance(perms, dict) and str(perms.get("*", "")).lower() == "allow":
        raise RuntimeError(
            f"Wildcard permissions still allow-all on {api_url}: {persisted}"
        )
    if isinstance(perms, dict) and str(perms.get("computer_use", "")).lower() != "ask":
        raise RuntimeError(
            f"computer_use permission must be ask on {api_url}: {persisted}"
        )


_HITL_PIN_BACKOFF_SEC = 1.5


def _hitl_pin_retry_policy() -> tuple[int, float]:
    try:
        from dev_gate_contract import (
            signoff_hitl_pin_max_attempts,
            signoff_hitl_pin_request_timeout_sec,
        )

        return (
            signoff_hitl_pin_max_attempts(),
            signoff_hitl_pin_request_timeout_sec(),
        )
    except ImportError:
        return 3, 15.0


def _pin_hitl_on_api_with_retry(api_url: str) -> None:
    """Retry transient loopback timeouts while pinning HITL mode."""
    max_attempts, request_timeout_sec = _hitl_pin_retry_policy()
    last_error: OSError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            _pin_hitl_on_api(api_url, request_timeout_sec=request_timeout_sec)
            return
        except OSError as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(_HITL_PIN_BACKOFF_SEC * attempt)
    if last_error is not None:
        raise RuntimeError(
            f"Failed to pin HITL securityConfig on {api_url} after "
            f"{max_attempts} attempts: {last_error}"
        ) from last_error


def ensure_e2e_onboarding_complete(*, api_url: str) -> None:
    """Mark onboarding complete on any SHPOIB private or shared API (bypasses http_json allowlist)."""
    _e2e_api_post_json(
        f"{api_url.rstrip('/')}/api/v1/config/onboarding/complete",
        {},
        timeout_sec=15.0,
    )


def ensure_e2e_hitl_mode(*, api_url: str | None = None) -> None:
    """Disable YOLO + auto-review so shell HITL approval dialogs appear.

    Agent-level ``yoloModeEnabled: false`` does not override user securityConfig
    (merge uses OR). LIVE approval E2E must pin global securityConfig on the
    target API (including SHPOIB private ``:180xx`` backends).

    Also pins shared ``:8080`` when it differs from the private API — SHPOIB UI
    may briefly stream via Next ``/api/v1`` proxy before ``__MYRM_E2E_API_BASE__``
    inject completes, and parallel LIVE tests leave YOLO on the shared backend.

    Signoff clarify SHPOIB pool (API-only warm) pins only the private backend;
    shared ``:8080`` may be down under parallel wave without blocking clarify warm.

    Also clears wildcard ``permissions.*=allow`` left by ``ensure_e2e_yolo_mode``.
    """
    targets: list[str] = []
    if api_url:
        targets.append(api_url.rstrip("/"))
    if os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() != "1":
        shared = shared_hot_e2e_api_base()
        if shared not in targets:
            targets.append(shared)
    for target in targets:
        _pin_hitl_on_api_with_retry(target)


STREAM_API_BINDING_JS = """(() => {
  const raw = window.__MYRM_E2E_RUNTIME__?.apiBase ?? window.__MYRM_E2E_API_BASE__ ?? '';
  const trimmed = String(raw).trim().replace(/\\/+$/, '');
  return {
    hasPrivateBinding: trimmed.length > 0,
    origin: trimmed,
    usesRelativeProxy: trimmed.length === 0,
  };
})()"""

WAIT_WORKSPACE_STREAM_JS = """(async () => {
  const wait = window.__MYRM_WAIT_WORKSPACE_STREAM__;
  if (typeof wait !== 'function') {
    return { ok: false, err: 'missing-wait-hook' };
  }
  return await wait(30000);
})()"""

CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS = """(() => {
  try {
    localStorage.removeItem('config-offline-queue');
  } catch (_) {}
  return { ok: true };
})()"""

PUT_E2E_CLEAR_SEARCH_CONFIG_JS = """(async () => {
  const privateApi = String(window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  if (!privateApi) {
    return { ok: false, err: 'no-api-base' };
  }
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const mirrorStore = async () => {
    window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
    try {
      const useConfigStore = (await import('/src/store/useConfigStore')).default;
      useConfigStore.setState({ searchServiceConfigs: [] });
    } catch (_) {
      /* optional FE store mirror */
    }
    try {
      const { getConfigSyncManager } = await import('@/services/config/ConfigSyncManager');
      getConfigSyncManager().set('searchServices', { searchServiceConfigs: [] });
    } catch (_) {
      /* cache-only mirror when sync import unavailable */
    }
  };
  const verifyEmpty = async () => {
    const verifyResp = await fetch(`${privateApi}/api/v1/config/searchServices`, { cache: 'no-store' });
    if (!verifyResp.ok) {
      return { ok: false, err: `fetch-${verifyResp.status}` };
    }
    const body = await verifyResp.json();
    const persisted = body?.value ?? body?.data?.value ?? body?.data ?? {};
    const configs = Array.isArray(persisted?.searchServiceConfigs)
      ? persisted.searchServiceConfigs
      : [];
    return { ok: configs.length === 0, configCount: configs.length };
  };
  try {
    localStorage.removeItem('config-offline-queue');
    window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
    const value = { searchServiceConfigs: [] };
    let lastPutStatus = 0;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const putResp = await fetch(`${privateApi}/api/v1/config/searchServices`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'web', value }),
        cache: 'no-store',
      });
      lastPutStatus = putResp.status;
      if (putResp.ok) {
        const verified = await verifyEmpty();
        await mirrorStore();
        return {
          ok: verified.ok === true,
          mode: 'put-ok',
          configCount: verified.configCount ?? null,
          err: verified.err ?? null,
        };
      }
      if (putResp.status >= 500 && attempt < 2) {
        await sleep(250 * (attempt + 1));
        continue;
      }
      break;
    }
    const verified = await verifyEmpty();
    if (verified.ok === true) {
      await mirrorStore();
      return {
        ok: true,
        mode: 'verify-fallback',
        putStatus: lastPutStatus,
        configCount: verified.configCount ?? 0,
      };
    }
    return {
      ok: false,
      err: lastPutStatus ? `put-${lastPutStatus}` : 'put-failed',
      configCount: verified.configCount ?? null,
      verifyErr: verified.err ?? null,
    };
  } catch (error) {
    return { ok: false, err: String(error) };
  }
})()"""

PUT_E2E_HITL_CONFIG_JS = """(async () => {
  const privateApi = String(window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  const sharedApi = 'http://127.0.0.1:8080';
  const targets = [...new Set([privateApi, sharedApi].filter(Boolean))];
  if (targets.length === 0) {
    return { ok: false, err: 'no-api-base' };
  }
  try {
    localStorage.removeItem('config-offline-queue');
    const value = {
      yoloModeEnabled: false,
      yoloModeEnabledAt: null,
      yoloModeTimeout: null,
      yolo_mode_enabled: false,
      yolo_mode_enabled_at: null,
      yolo_mode_timeout: null,
      autoModeEnabled: false,
      autoReviewEnabled: false,
      planConfirmEnabled: false,
      domainHitlEnabled: false,
      approvalTimeoutBehavior: 'deny',
      permissions: { shell_exec: 'ask', code_interpreter: 'ask', computer_use: 'ask' },
    };
    const results = [];
    for (const api of targets) {
      const putResp = await fetch(`${api}/api/v1/config/securityConfig`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deviceId: 'web', value }),
        cache: 'no-store',
      });
      if (!putResp.ok) {
        results.push({ api, ok: false, err: `put-${putResp.status}` });
        continue;
      }
      const verifyResp = await fetch(`${api}/api/v1/config/securityConfig`, { cache: 'no-store' });
      if (!verifyResp.ok) {
        results.push({ api, ok: false, err: `fetch-${verifyResp.status}` });
        continue;
      }
      const body = await verifyResp.json();
      const persisted = body?.value ?? body?.data?.value ?? body?.data ?? {};
      const yolo = Boolean(persisted?.yoloModeEnabled || persisted?.yolo_mode_enabled);
      const perms = persisted?.permissions;
      const wildcardAllow =
        typeof perms === 'object' &&
        perms !== null &&
        String(perms['*'] || '').toLowerCase() === 'allow';
      const computerUseAsk =
        typeof perms === 'object' &&
        perms !== null &&
        String(perms['computer_use'] || '').toLowerCase() === 'ask';
      results.push({
        api,
        ok: !yolo && !wildcardAllow && computerUseAsk,
        yoloModeEnabled: yolo,
        wildcardAllow,
        computerUseAsk,
      });
    }
    try {
      const { getConfigSyncManager } = await import('@/services/config/ConfigSyncManager');
      getConfigSyncManager().set('securityConfig', value);
    } catch (_) {
      /* E2E pin still valid via server PUT when local sync import fails */
    }
    return {
      ok: results.every((row) => row.ok),
      results,
    };
  } catch (error) {
    return { ok: false, err: String(error), targets };
  }
})()"""


async def ensure_e2e_hitl_mode_in_browser(chat: object) -> None:
    """PUT HITL securityConfig on the bound private API and clear ConfigSync drift."""
    await chat.evaluate(CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS, await_promise=False)  # type: ignore[attr-defined]
    raw = await chat.evaluate(PUT_E2E_HITL_CONFIG_JS, await_promise=True)  # type: ignore[attr-defined]
    observed = raw if isinstance(raw, dict) else {"value": raw}
    if observed.get("ok") is not True:
        raise RuntimeError(f"Browser HITL pin failed: {observed}")


def clear_search_services_ssot(*, api_url: str | None = None) -> None:
    """Python SSOT: empty searchServices on the bound E2E API, with verify."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    put_config_value(
        "searchServices",
        {"searchServiceConfigs": []},
        api_url=resolved,
    )
    value = fetch_config_value("searchServices", api_url=resolved)
    configs = value.get("searchServiceConfigs")
    if configs != []:
        raise RuntimeError(
            f"searchServices must be empty after Python PUT, got {value!r} api={resolved}"
        )


async def ensure_e2e_search_cleared_in_browser(
    chat: object,
    *,
    api_url: str | None = None,
    recv_timeout_sec: float = 45.0,
    max_attempts: int = 2,
) -> None:
    """Clear searchServices: Python SSOT first, then browser mirror (PUT retry + verify fallback)."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    recv_timeout = min(60.0, max(10.0, float(recv_timeout_sec)))
    attempts = max(1, int(max_attempts))
    python_ssot_timeout = min(20.0, recv_timeout)
    await asyncio.wait_for(
        asyncio.to_thread(clear_search_services_ssot, api_url=resolved),
        timeout=python_ssot_timeout,
    )
    await chat.evaluate(  # type: ignore[attr-defined]
        CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS,
        await_promise=False,
        recv_timeout=min(20.0, recv_timeout),
    )
    last_err: object = None
    for attempt in range(attempts):
        try:
            raw = await chat.evaluate(  # type: ignore[attr-defined]
                PUT_E2E_CLEAR_SEARCH_CONFIG_JS,
                await_promise=True,
                recv_timeout=recv_timeout,
            )
        except TimeoutError as exc:
            last_err = exc
            if attempt + 1 >= attempts:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
            continue
        observed = raw if isinstance(raw, dict) else {"value": raw}
        if observed.get("ok") is True:
            return
        last_err = observed
        if attempt + 1 < attempts:
            await asyncio.sleep(1.0)
            continue
        break
    # Last resort: Python SSOT still empty → accept FE mirror failure only if verify holds.
    value = await asyncio.wait_for(
        asyncio.to_thread(fetch_config_value, "searchServices", api_url=resolved),
        timeout=python_ssot_timeout,
    )
    configs = value.get("searchServiceConfigs")
    if configs == []:
        return
    raise RuntimeError(
        f"Browser search clear failed: {last_err}; persisted={value!r}; api={resolved}"
    )


async def hard_reset_e2e_hitl_mode(
    chat: object,
    *,
    api_url: str,
    page_url: str,
) -> None:
    """Pin HITL on API, reload UI to reset ConfigSync cache, then pin again."""
    ensure_e2e_hitl_mode(api_url=api_url)
    ensure_e2e_onboarding_complete(api_url=api_url)
    await ensure_e2e_hitl_mode_in_browser(chat)
    await chat.cdp("Page.reload", recv_timeout=120.0)  # type: ignore[attr-defined]
    await chat.bootstrap(page_url, timeout_sec=120.0)  # type: ignore[attr-defined]
    ensure_e2e_hitl_mode(api_url=api_url)
    ensure_e2e_onboarding_complete(api_url=api_url)
    await ensure_e2e_hitl_mode_in_browser(chat)


def ensure_e2e_memory_disabled(*, api_url: str | None = None) -> None:
    """Disable memory for live agent E2E to avoid poisoned procedural briefs."""
    personal = fetch_config_value("personalSettings", api_url=api_url)
    merged: dict[str, object] = {
        **personal,
        "enableMemory": False,
        "enableMemoryAutoExtraction": False,
    }
    put_config_value("personalSettings", merged, api_url=api_url)


def deny_stale_browser_takeover_approvals(*, api_url: str | None = None) -> int:
    """Deny orphan PENDING browser_takeover approvals before LIVE Chrome E2E."""
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    denied = 0
    try:
        payload = _e2e_api_get_json(
            f"{resolved_api}/api/v1/approvals?limit=50&offset=0",
            timeout_sec=15.0,
        )
    except Exception:
        return 0
    records = payload.get("approvals") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        if (
            raw.get("action_type") != "browser_takeover"
            or raw.get("status") != "PENDING"
        ):
            continue
        approval_id = str(raw.get("id") or raw.get("approval_id") or "").strip()
        if not approval_id:
            continue
        try:
            _e2e_api_post_json(
                f"{resolved_api}/api/v1/approvals/{approval_id}/resolve",
                {"decision": "deny"},
                timeout_sec=15.0,
            )
            denied += 1
        except Exception:
            continue
    return denied


def chat_messages_have_done(
    chat_id: str,
    *,
    min_user_count: int = 1,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
) -> bool:
    messages = fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
    )
    user_count = sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )
    if user_count < min_user_count:
        return False
    last_assistant: dict[str, object] | None = None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            last_assistant = msg
    if last_assistant is None:
        return False
    content = str(last_assistant.get("content") or "")
    return bool(_DONE_REPLY_RE.search(content))


def wait_chat_messages_done(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 120.0,
    fetch_timeout_sec: float = 15.0,
    progress_interval_sec: float = 30.0,
    on_tick: Callable[[], None] | None = None,
) -> bool:
    """Poll chat REST until assistant DONE or timeout (STREAM_CONVERGE SSOT)."""
    deadline = time.monotonic() + timeout_sec
    last_progress_at = time.monotonic()
    while time.monotonic() < deadline:
        if on_tick is not None:
            on_tick()
        try:
            if chat_messages_have_done(
                chat_id,
                api_url=api_url,
                timeout_sec=fetch_timeout_sec,
            ):
                return True
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            print(
                f"E2E_WAIT_API_DONE_SKIP: transient messages poll — {exc!s:.120}",
                flush=True,
            )
        now = time.monotonic()
        if now - last_progress_at >= progress_interval_sec:
            try:
                messages = fetch_chat_messages(
                    chat_id,
                    api_url=api_url,
                    timeout_sec=fetch_timeout_sec,
                )
                assistant_tail = next(
                    (
                        str(msg.get("content") or "")[:80]
                        for msg in reversed(messages)
                        if isinstance(msg, dict) and msg.get("role") == "assistant"
                    ),
                    "",
                )
                print(
                    f"E2E_WAIT_API_DONE_PROGRESS: chatId={chat_id} "
                    f"messages={len(messages)} assistant_tail={assistant_tail!r} "
                    f"remaining={int(deadline - now)}s",
                    flush=True,
                )
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                print(
                    f"E2E_WAIT_API_DONE_PROGRESS_SKIP: {exc!s:.120}",
                    flush=True,
                )
            last_progress_at = now
        time.sleep(2.0)
    return False


def _sse_message_text(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "message":
            continue
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
    return "".join(chunks)


def _collect_agent_stream_events(
    payload: dict[str, object],
    *,
    api_url: str | None = None,
    timeout_sec: float = 180.0,
    stop_on_clarification: bool = False,
) -> dict[str, object]:
    """POST agent-stream and collect SSE until deadline, idle, or terminal event."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    req = urllib.request.Request(  # noqa: S310
        f"{resolved}/api/v1/agents/agent-stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events: list[dict[str, object]] = []
    error_event: dict[str, object] | None = None
    deadline = time.monotonic() + timeout_sec
    idle_timeout_sec = min(45.0, max(15.0, timeout_sec / 3.0))
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        # Signoff clarify/API legs: parallel wave load can stall SSE >45s between tokens.
        idle_timeout_sec = signoff_parallel_force_chat_timeout_sec(45.0)
        idle_timeout_sec = min(120.0, max(idle_timeout_sec, timeout_sec * 0.5))
        if os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1":
            # SHPOIB pool: agent may stall >120s between progress and ask_question under wave load.
            idle_timeout_sec = min(240.0, max(idle_timeout_sec, timeout_sec * 0.85))
    last_event_at = time.monotonic()
    connect_timeout_sec = min(30.0, max(5.0, timeout_sec / 3.0))
    clarification_seen = False
    post_clarify_deadline: float | None = None
    try:
        with _e2e_api_urlopen(req, timeout_sec=connect_timeout_sec) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                body = resp.read().decode("utf-8", errors="replace")
                return {
                    "events": events,
                    "error": {
                        "type": "error",
                        "error_type": "AgentStreamHttpError",
                        "status": status,
                        "body": body[:500],
                    },
                }
            while time.monotonic() < deadline:
                now = time.monotonic()
                skip_idle_break = (
                    stop_on_clarification
                    and os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip()
                    == "1"
                )
                if not skip_idle_break and now - last_event_at >= idle_timeout_sec:
                    error_event = {
                        "type": "error",
                        "error_type": "AgentStreamIdleTimeout",
                        "error": (
                            "agent-stream idle timeout "
                            f"after {idle_timeout_sec:.0f}s without SSE data"
                        ),
                    }
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                _set_http_response_read_timeout(resp, min(30.0, remaining))
                try:
                    line_bytes = resp.readline()
                except TimeoutError:
                    continue
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                events.append(data)
                last_event_at = time.monotonic()
                if data.get("type") == "error":
                    error_event = data
                    break
                if (
                    stop_on_clarification
                    and data.get("type") == "clarification_required"
                ):
                    clarification_seen = True
                    post_clarify_deadline = time.monotonic() + min(
                        15.0,
                        max(5.0, timeout_sec / 6.0),
                    )
                    continue
                if stop_on_clarification and clarification_seen:
                    if raw == "[DONE]" or data.get("type") == "message_end":
                        break
                    if (
                        post_clarify_deadline is not None
                        and time.monotonic() >= post_clarify_deadline
                    ):
                        break
                    continue
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        error_event = {
            "type": "error",
            "error_type": (
                "AgentBusyError" if exc.code in {409, 423} else "AgentStreamHttpError"
            ),
            "status": exc.code,
            "error": f"HTTP Error {exc.code}: {exc.reason}",
            "body": body[:500],
        }
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        error_event = {
            "type": "error",
            "error_type": "AgentStreamConnectTimeout",
            "error": str(exc),
        }

    if stop_on_clarification and error_event is None and not clarification_seen:
        event_types = sorted(
            {
                str(event.get("type"))
                for event in events
                if isinstance(event, dict) and event.get("type") is not None
            }
        )
        error_event = {
            "type": "error",
            "error_type": "AgentStreamClarifyIncomplete",
            "error": (
                "agent-stream ended without clarification_required "
                f"within {timeout_sec:.0f}s"
            ),
            "event_types": event_types,
        }

    return {
        "events": events,
        "error": error_event,
    }


def start_clarify_turn_via_api(
    chat_id: str,
    *,
    query: str,
    model_selection: dict[str, object],
    api_url: str | None = None,
    timeout_sec: float = 120.0,
) -> dict[str, object]:
    """POST agent-stream until clarification_required (signoff chrome send fallback)."""
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": str(query),
        "modelSelection": model_selection,
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["structured_clarify"]},
        "engineParams": {"signoffClarifyContract": True},
    }
    collected = _collect_agent_stream_events(
        payload,
        api_url=api_url,
        timeout_sec=timeout_sec,
        stop_on_clarification=True,
    )
    events = collected.get("events")
    error_event = collected.get("error")
    if not isinstance(events, list):
        events = []
    has_clarification = any(
        isinstance(event, dict) and event.get("type") == "clarification_required"
        for event in events
    )
    event_types = sorted(
        {
            str(event.get("type"))
            for event in events
            if isinstance(event, dict) and event.get("type") is not None
        }
    )
    return {
        "ok": error_event is None and has_clarification,
        "has_clarification": has_clarification,
        "events": events,
        "event_types": event_types,
        "error": error_event,
    }


def resume_clarify_skip_via_api(
    chat_id: str,
    *,
    model_selection: dict[str, object],
    api_url: str | None = None,
    timeout_sec: float = 180.0,
    query: str = "",
) -> dict[str, object]:
    """POST agent-stream with resumeValue {} (Skip parity) on the private E2E backend."""
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": str(query),
        "modelSelection": model_selection,
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["structured_clarify"]},
        "resumeValue": {},
    }
    collected = _collect_agent_stream_events(
        payload,
        api_url=api_url,
        timeout_sec=timeout_sec,
        stop_on_clarification=False,
    )
    events = collected.get("events")
    error_event = collected.get("error")
    if not isinstance(events, list):
        events = []

    final_text = _sse_message_text(events)
    event_types = sorted(
        {
            str(event.get("type"))
            for event in events
            if isinstance(event, dict) and event.get("type") is not None
        }
    )
    ok = (
        error_event is None
        and bool(events)
        and "error" not in event_types
        and event_types != ["clarification_required"]
        and (
            "message_end" in event_types
            or "DONE-SKIPPED" in final_text.upper()
            or "message" in event_types
        )
    )
    return {
        "ok": ok,
        "events": events,
        "event_types": event_types,
        "final_text": final_text,
        "error": error_event,
    }


def is_hitl_already_resolved_by_timeout(result: dict[str, object]) -> bool:
    """True when resume/skip hit terminal HITL timeout resolution (409, non-retryable)."""
    error = result.get("error")
    if not isinstance(error, dict):
        return False
    if error.get("error_type") != "AgentBusyError":
        return False
    fragments: list[str] = []
    for key in ("error", "body", "detail"):
        raw = error.get(key)
        if raw is not None:
            fragments.append(str(raw))
    combined = " ".join(fragments).lower()
    return (
        "already been resolved by timeout" in combined
        or "resolved by timeout" in combined
    )


def clarify_skip_resume_should_retry(result: dict[str, object]) -> bool:
    """True when SSE ended early (e.g. UI stream still holds agent) and retry may succeed."""
    if result.get("ok") is True:
        return False
    if is_hitl_already_resolved_by_timeout(result):
        return False
    error = result.get("error")
    if isinstance(error, dict) and error.get("error_type") in {
        "AgentBusyError",
        "AgentStreamClarifyIncomplete",
        "AgentStreamIdleTimeout",
    }:
        return True
    events = result.get("events")
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("error_type") == "AgentBusyError":
                return True
            if (
                event.get("type") == "error"
                and event.get("error_type") == "AgentBusyError"
            ):
                return True
    event_types = result.get("event_types")
    if not isinstance(event_types, list):
        return False
    normalized = {str(item) for item in event_types}
    if normalized == {"progress"}:
        return True
    if normalized == {"error"}:
        return True
    return False


def _assistant_clarification_from_message(
    msg: dict[str, object],
) -> dict[str, object] | None:
    if msg.get("role") != "assistant":
        return None
    for key in ("metadata", "extra_data"):
        container = msg.get(key)
        if not isinstance(container, dict):
            continue
        clarification = container.get("clarification")
        if isinstance(clarification, dict):
            return clarification
    return None


def chat_has_pending_clarification(chat_id: str, *, api_url: str | None = None) -> bool:
    """Return True when chat messages show unanswered structured clarify (API SSOT)."""
    normalized = chat_id.strip()
    if not normalized:
        return False
    try:
        messages = fetch_chat_messages(normalized, api_url=api_url)
    except (TimeoutError, OSError, urllib.error.URLError):
        # SHPOIB/shared backend may stall under parallel LIVE load; treat as not-ready.
        return False
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        clarification = _assistant_clarification_from_message(msg)
        if clarification is None:
            continue
        if clarification.get("answered") is False:
            return True
        if clarification.get("answered") is True:
            return False
    return False


def chat_messages_have_clarify_skip_done(
    chat_id: str, *, min_user_count: int = 1, api_url: str | None = None
) -> bool:
    """Return True when the last assistant message shows clarify Skip resume completed."""
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    user_count = sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )
    if user_count < min_user_count:
        return False
    last_assistant: dict[str, object] | None = None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            last_assistant = msg
    if last_assistant is None:
        return False
    content = str(last_assistant.get("content") or "")
    return bool(_CLARIFY_SKIP_DONE_RE.search(content))


BRIDGE_CHAT_ID_JS = """
(() => {
  const chatId = window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.chatId;
  return typeof chatId === 'string' && chatId.trim() ? chatId.trim() : null;
})()
""".strip()

BRIDGE_TURN_SNAPSHOT_JS = """
(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.();
  return snap && typeof snap === 'object' ? snap : null;
})()
""".strip()


def backend_log_path() -> Path:
    override = os.getenv("MYRM_BACKEND_LOG", "").strip()
    if not override:
        override = os.getenv("MYRM_BACKEND_LOG_FILE", "").strip()
    if override:
        return Path(override)
    state_dir = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    if state_dir:
        return Path(state_dir) / "backend.log"
    default = Path.home() / ".local/state/myrm-dev/backend.log"
    if default.is_file():
        return default
    server_root = Path(__file__).resolve().parents[3] / "myrm-agent-server"
    return server_root / ".myrm-dev-backend.log"


def snapshot_backend_log_offset() -> int:
    path = backend_log_path()
    if not path.is_file():
        return 0
    return path.stat().st_size


def count_execution_cache_in_log(*, since_offset: int) -> tuple[int, int]:
    path = backend_log_path()
    if not path.is_file():
        return 0, 0
    with path.open("rb") as handle:
        handle.seek(since_offset)
        chunk = handle.read()
    text = chunk.decode("utf-8", errors="replace")
    created = text.count("execution_cache_created")
    reused = text.count("execution_cache_reuse")
    return created, reused


def count_turn_prewarm_in_log(*, since_offset: int) -> int:
    """Count ``Turn prewarm requested`` log lines (EmptyChat / focus proactive warm)."""
    path = backend_log_path()
    if not path.is_file():
        return 0
    with path.open("rb") as handle:
        handle.seek(since_offset)
        chunk = handle.read()
    text = chunk.decode("utf-8", errors="replace")
    return text.count("Turn prewarm requested")
