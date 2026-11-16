"""Scripts evaluated in the chat page.

[INPUT]
- none: constant scripts

[OUTPUT]
- PAGE_PROBE_JS, MODEL_PROBE_JS, BRIDGE_CHAT_ID_JS, BRIDGE_TURN_SNAPSHOT_JS: page and bridge probes
- SELECT_MIMO_MODEL_JS, SELECT_FIRST_ENABLED_MODEL_JS, DISMISS_MODALS_JS, RESET_CHAT_JS, PREPARE_AUTOMATION_SEND_JS: page actions
- E2E_BRIDGE_INSTALL_JS, STREAM_API_BINDING_JS, WAIT_WORKSPACE_STREAM_JS: bridge installer and stream API binding

[POS]
Scripts the E2E evaluates in the chat page: probes, model selection, modal dismissal, chat reset, the E2E bridge installer and the stream API binding. Pure strings: the binding scripts live in `binding`, the config pin scripts in `config.page_scripts`.
"""

from __future__ import annotations

PREPARE_AUTOMATION_SEND_JS = """
(() => {
  window.__MYRM_E2E_CHAT__?.prepareAutomationSend?.();
  return { ok: true };
})()
""".strip()

PAGE_PROBE_JS = """
(() => {
  const input = document.querySelector('[data-chat-input]');
  const layout = document.querySelector('[data-testid="app-layout"]');
  const skeleton = !!document.querySelector('[aria-label="Loading messages"]');
  const anyReactKey = (el) => el ? Object.keys(el).find((k) => k.startsWith('__react') || k.includes('react')) : null;
  const fiberKey = anyReactKey(input);
  const layoutFiberKey = anyReactKey(layout);
  const isHydrated = !!fiberKey || !!layoutFiberKey || !!window.__MYRM_E2E_CHAT__;
  return {
    hasInput: !!input,
    clientHydrated: isHydrated,
    hasBridge: !!window.__MYRM_E2E_CHAT__,
    skeleton,
    hasLayout: !!layout,
    path: location.pathname,
    href: location.href,
    bodySnippet: (document.body?.innerText || '').slice(0, 200),
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
    localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
    localStorage.setItem('myrm_onboarding_complete', 'true');
    localStorage.setItem('myrm_boot_shown', '1');
  } catch (err) {
    return { ok: false, err: String(err), href: location.href };
  }
  Array.from(document.querySelectorAll('button')).forEach((b) => {
    const text = (b.textContent || '').trim();
    if (/稍后再说|Later|Skip for now|关闭|Dismiss|Not now|跳过|Skip|全部拒绝|Reject all/i.test(text)) {
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
