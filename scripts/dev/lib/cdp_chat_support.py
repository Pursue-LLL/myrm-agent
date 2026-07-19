"""Shared scripts and observations for Chrome chat UI E2E."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

_E2E_RUNTIME_BINDING_PREFIX = "myrm-e2e-v1:"
_E2E_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")

def get_e2e_api_url() -> str:
    return os.getenv("E2E_API_BASE", "http://127.0.0.1:8080").rstrip("/")


def get_e2e_ui_url() -> str:
    return os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
_OK_REPLY_RE = re.compile(r"(?:\bOK\b|GOAL_OK)", re.IGNORECASE)
_DONE_REPLY_RE = re.compile(r"\bDONE\b", re.IGNORECASE)


def resolve_e2e_api_base(api_base: str | None = None) -> str:
    return (api_base or os.getenv("E2E_API_BASE", "")).strip().rstrip("/")


def e2e_runtime_binding(api_base: str | None = None) -> dict[str, object] | None:
    """Return a validated page-local private Backend binding."""
    base = resolve_e2e_api_base(api_base)
    runtime_id = os.getenv("MYRM_E2E_PRIVATE_RUNTIME_ID", "").strip()
    run_id = os.getenv("MYRM_E2E_RUN_ID", "").strip()
    ui_base = get_e2e_ui_url()
    if not base or not runtime_id or not run_id:
        return None
    if not _E2E_RUNTIME_ID_RE.fullmatch(runtime_id) or not _E2E_RUNTIME_ID_RE.fullmatch(run_id):
        raise RuntimeError("E2E runtime/run identity contains unsupported characters")
    api = urlsplit(base)
    ui = urlsplit(ui_base)
    loopback_hosts = {"127.0.0.1", "localhost"}
    if (
        api.scheme not in {"http", "https"}
        or ui.scheme not in {"http", "https"}
        or api.hostname not in loopback_hosts
        or ui.hostname not in loopback_hosts
        or not api.port
        or not ui.port
    ):
        raise RuntimeError("E2E runtime binding only permits explicit loopback HTTP origins")
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


def _api_provider_ready() -> bool:
    try:
        resp = urllib.request.urlopen(  # noqa: S310 - fixed loopback E2E endpoint
            f"{get_e2e_api_url()}/api/v1/config/readiness",
            timeout=5,
        )
        payload = json.loads(resp.read())
    except Exception:
        return False
    provider = payload.get("provider")
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


def fetch_provider_readiness_snapshot() -> dict[str, object]:
    """Return private-pool provider readiness for E2E failure diagnostics."""
    api_base = get_e2e_api_url()
    try:
        resp = urllib.request.urlopen(  # noqa: S310
            f"{api_base}/api/v1/config/readiness",
            timeout=5,
        )
        payload = json.loads(resp.read())
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
    timeout_sec: float = 60.0,
    poll_interval_sec: float = 1.0,
) -> bool:
    """Poll private-pool readiness until provider seed is ready (SHPOIB bootstrap race)."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _api_provider_ready():
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
        resp = urllib.request.urlopen(  # noqa: S310
            f"{resolved_api}/api/v1/goals/{chat_id}/status",
            timeout=15,
        )
        payload = json.loads(resp.read())
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
            return {"ok": False, "err": "resume-failed", "payload": resume, "prior_status": status}
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
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        f"{resolved_api}/api/v1/goals/{chat_id}/status",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read())
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
  sessionStorage.setItem('migration_discovery_dismissed', 'true');
  sessionStorage.setItem('competitor_migration_dismissed', 'true');
  Array.from(document.querySelectorAll('button')).forEach((b) => {
    const text = (b.textContent || '').trim();
    if (/稍后再说|Later|Skip for now|关闭|Dismiss|Not now|打开迁移向导/i.test(text)) {
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
    if (existing?.setInputMessage && existing?.handleSubmit && !existing.__e2eFallback) {
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
            with urllib.request.urlopen(base_url.rstrip("/") + "/", timeout=45) as resp:
                if resp.status == 200:
                    return
                last_error = f"HTTP {resp.status}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(3)
    raise TimeoutError(f"Frontend warmup failed within {timeout_sec:.0f}s: {last_error}")


def fetch_chat_messages(chat_id: str, *, api_url: str | None = None) -> list[dict[str, object]]:
    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
    req = urllib.request.Request(
        f"{resolved_api}/api/v1/chats/{chat_id}/messages",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    messages = data.get("messages")
    return messages if isinstance(messages, list) else []


def chat_user_message_count(chat_id: str, *, api_url: str | None = None) -> int:
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    return sum(1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user")


def chat_messages_have_ok(chat_id: str, *, min_user_count: int = 1, api_url: str | None = None) -> bool:
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    user_count = sum(1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user")
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
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        raw = resp.read()
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"value": payload}


def fetch_config_value(config_key: str, *, api_url: str | None = None) -> dict[str, object]:
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
            resp = urllib.request.urlopen(  # noqa: S310
                f"{resolved_api}/api/v1/health",
                timeout=5,
            )
            payload = json.loads(resp.read())
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


def ensure_e2e_memory_disabled(*, api_url: str | None = None) -> None:
    """Disable memory for live agent E2E to avoid poisoned procedural briefs."""
    personal = fetch_config_value("personalSettings", api_url=api_url)
    merged: dict[str, object] = {
        **personal,
        "enableMemory": False,
        "enableMemoryAutoExtraction": False,
    }
    put_config_value("personalSettings", merged, api_url=api_url)


def chat_messages_have_done(chat_id: str, *, min_user_count: int = 1, api_url: str | None = None) -> bool:
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    user_count = sum(1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user")
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
