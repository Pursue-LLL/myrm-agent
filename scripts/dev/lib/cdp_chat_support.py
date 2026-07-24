"""Shared scripts and observations for Chrome chat UI E2E."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
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


def shpoib_parallel_shell_timeout_sec(timeout_sec: float) -> float:
    """Extend shell hydration budget for parallel SHPOIB chrome_e2e on shared :3000."""
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return timeout_sec
    base_floor = max(timeout_sec, 180.0)
    active_leases = 0
    try:
        from stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[4]
        active_leases = wave_active_lease_count(monorepo_root)
    except Exception:
        active_leases = 0
    scaled = max(base_floor, 180.0 + active_leases * 45.0)
    return min(scaled, 420.0)


def shpoib_shell_wait_slice_cap(remaining_sec: float) -> float:
    """Per-iteration cap for MCP shell wait loops (parallel SHPOIB needs >60s)."""
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
    deadline = time.monotonic() + timeout_sec
    health_ok = False
    while time.monotonic() < deadline:
        if not health_ok:
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
        if health_ok and _api_provider_ready(api_url=api_url):
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
    chat_id: str, *, api_url: str | None = None
) -> list[dict[str, object]]:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    req = urllib.request.Request(  # noqa: S310 - validated in _e2e_api_urlopen
        f"{resolved_api}/api/v1/chats/{chat_id}/messages",
        headers={"Accept": "application/json"},
    )
    try:
        with _e2e_api_urlopen(req, timeout_sec=15) as resp:
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


def chat_user_message_count(chat_id: str, *, api_url: str | None = None) -> int:
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    return sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )


def chat_messages_have_ok(
    chat_id: str, *, min_user_count: int = 1, api_url: str | None = None
) -> bool:
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
    return bool(_OK_REPLY_RE.search(content))


def _config_http_json(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
    *,
    api_url: str | None = None,
) -> dict[str, object]:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(  # noqa: S310
        f"{resolved_api}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    with _e2e_api_urlopen(req, timeout_sec=30) as resp:  # noqa: S310
        raw = resp.read()
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"value": payload}


def fetch_config_value(
    config_key: str, *, api_url: str | None = None
) -> dict[str, object]:
    payload = _config_http_json("GET", f"/api/v1/config/{config_key}", api_url=api_url)
    value = payload.get("value")
    return value if isinstance(value, dict) else {}


def put_config_value(
    config_key: str,
    value: dict[str, object],
    *,
    api_url: str | None = None,
) -> None:
    _config_http_json(
        "PUT",
        f"/api/v1/config/{config_key}",
        {"deviceId": "web", "value": value},
        api_url=api_url,
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
    current = fetch_config_value("securityConfig", api_url=api_url)
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
        },
    }


def _pin_hitl_on_api(api_url: str) -> None:
    current = fetch_config_value("securityConfig", api_url=api_url)
    put_config_value("securityConfig", _hitl_security_payload(current), api_url=api_url)
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
        with _e2e_api_urlopen(reset_req, timeout_sec=15.0) as reset_resp:
            if reset_resp.status != 200:
                body = reset_resp.read(500)
                raise RuntimeError(
                    f"reset-hitl-runtime failed on {api_url}: {reset_resp.status} {body!r}"
                )
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    persisted = fetch_config_value("securityConfig", api_url=api_url)
    if persisted.get("yoloModeEnabled") or persisted.get("yolo_mode_enabled"):
        raise RuntimeError(
            f"Failed to disable YOLO securityConfig on {api_url}: {persisted}"
        )
    perms = persisted.get("permissions")
    if isinstance(perms, dict) and str(perms.get("*", "")).lower() == "allow":
        raise RuntimeError(
            f"Wildcard permissions still allow-all on {api_url}: {persisted}"
        )


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

    Also clears wildcard ``permissions.*=allow`` left by ``ensure_e2e_yolo_mode``.
    """
    targets: list[str] = []
    if api_url:
        targets.append(api_url.rstrip("/"))
    shared = shared_hot_e2e_api_base()
    if shared not in targets:
        targets.append(shared)
    for target in targets:
        _pin_hitl_on_api(target)


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
      permissions: { shell_exec: 'ask', code_interpreter: 'ask' },
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
      results.push({ api, ok: !yolo && !wildcardAllow, yoloModeEnabled: yolo, wildcardAllow });
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
) -> None:
    """Clear searchServices: Python SSOT first, then browser mirror (PUT retry + verify fallback)."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    clear_search_services_ssot(api_url=resolved)
    await chat.evaluate(CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS, await_promise=False)  # type: ignore[attr-defined]
    raw = await chat.evaluate(PUT_E2E_CLEAR_SEARCH_CONFIG_JS, await_promise=True)  # type: ignore[attr-defined]
    observed = raw if isinstance(raw, dict) else {"value": raw}
    if observed.get("ok") is True:
        return
    # Last resort: Python SSOT still empty → accept FE mirror failure only if verify holds.
    value = fetch_config_value("searchServices", api_url=resolved)
    configs = value.get("searchServiceConfigs")
    if configs == []:
        return
    raise RuntimeError(
        f"Browser search clear failed: {observed}; persisted={value!r}; api={resolved}"
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
    chat_id: str, *, min_user_count: int = 1, api_url: str | None = None
) -> bool:
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
    return bool(_DONE_REPLY_RE.search(content))


def _sse_message_text(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "message":
            continue
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
    return "".join(chunks)


def resume_clarify_skip_via_api(
    chat_id: str,
    *,
    model_selection: dict[str, object],
    api_url: str | None = None,
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    """POST agent-stream with resumeValue {} (Skip parity) on the private E2E backend."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "",
        "modelSelection": model_selection,
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["structured_clarify"]},
        "resumeValue": {},
    }
    req = urllib.request.Request(  # noqa: S310
        f"{resolved}/api/v1/agents/agent-stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events: list[dict[str, object]] = []
    error_event: dict[str, object] | None = None
    deadline = time.monotonic() + timeout_sec
    with _e2e_api_urlopen(req, timeout_sec=timeout_sec) as resp:
        status = getattr(resp, "status", 200)
        if status != 200:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": False,
                "status": status,
                "body": body[:500],
                "events": events,
                "event_types": [],
                "final_text": "",
                "error": None,
            }
        while time.monotonic() < deadline:
            line_bytes = resp.readline()
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
            if data.get("type") == "error":
                error_event = data
                break

    final_text = _sse_message_text(events)
    event_types = sorted(
        {str(event.get("type")) for event in events if event.get("type") is not None}
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


def clarify_skip_resume_should_retry(result: dict[str, object]) -> bool:
    """True when SSE ended early (e.g. UI stream still holds agent) and retry may succeed."""
    if result.get("ok") is True:
        return False
    error = result.get("error")
    if isinstance(error, dict) and error.get("error_type") == "AgentBusyError":
        return True
    event_types = result.get("event_types")
    if not isinstance(event_types, list):
        return False
    normalized = {str(item) for item in event_types}
    if normalized == {"progress"}:
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


def chat_has_pending_clarification(
    chat_id: str, *, api_url: str | None = None
) -> bool:
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
