"""Shared scripts and observations for Chrome chat UI E2E."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

def get_e2e_api_url() -> str:
    return os.getenv("E2E_API_BASE", "http://127.0.0.1:8080").rstrip("/")


# Backward-compatible alias; always resolve dynamically for SHPOIB private pools.
API_URL = get_e2e_api_url()
_OK_REPLY_RE = re.compile(r"(?:\bOK\b|GOAL_OK)", re.IGNORECASE)


def e2e_api_base_inject_js(api_base: str | None = None) -> str:
    base = (api_base or os.getenv("E2E_API_BASE", "")).strip().rstrip("/")
    if not base:
        return "(() => ({ ok: false, err: 'no-api-base' }))()"
    encoded = json.dumps(base)
    return f"""(() => {{
  window.__MYRM_E2E_API_BASE__ = {encoded};
  return {{ ok: true, base: {encoded} }};
}})()"""


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
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = str(msg.get("content") or "")
        if _OK_REPLY_RE.search(content):
            return True
    return False


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

