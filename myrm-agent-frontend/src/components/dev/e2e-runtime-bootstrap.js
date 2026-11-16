/**
 * [INPUT]
 * - cdp_chat.support.binding::e2e_runtime_binding_source (POS: Binds the chat page to the backend under test: the scripts that put the runtime identity and API base into the page, and the check that the page reports the expected one) — writes the `myrm-e2e-v1:` JSON binding into `window.name` before the page loads
 * - GET /api/v1/health of the bound backend — returns the `runtime_id` the binding is checked against
 *
 * [OUTPUT]
 * - window.__MYRM_E2E_RUNTIME__, __MYRM_E2E_API_BASE__, __MYRM_E2E_RUNTIME_READY__ and the `myrm_e2e_runtime_ready` event: the verified binding and its readiness
 * - window.__MYRM_DIAG_ERRORS__: page errors collected from the first script on (the bridge diagnostics read it)
 * - fetch / XMLHttpRequest / EventSource / WebSocket calls to `/api/v1` and `/webui` rerouted to the bound private backend
 *
 * [POS]
 * 把页面绑定到已校验的 E2E 私有后端的运行时绑定脚本。没有校验通过的绑定（页面与后端都是回环地址、`uiOrigin` 与页面同源）时什么都不做；
 * 只在非生产构建里由 `app/e2e-runtime-bootstrap.js/route.ts` 提供，根布局以 `beforeInteractive` 脚本引入。
 */
(() => {
  'use strict';

  const PREFIX = 'myrm-e2e-v1:';
  const raw = window.name;
  if (!raw.startsWith(PREFIX)) {
    return;
  }

  const isLoopback = (hostname) => hostname === '127.0.0.1' || hostname === 'localhost';
  const isIdentifier = (value) => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(value);

  let binding;
  try {
    binding = JSON.parse(raw.slice(PREFIX.length));
    const api = new URL(binding.apiBase);
    if (
      binding.version !== 1 ||
      !isIdentifier(binding.runId) ||
      !isIdentifier(binding.runtimeId) ||
      !isLoopback(location.hostname) ||
      !isLoopback(api.hostname) ||
      binding.uiOrigin !== location.origin ||
      (api.protocol !== 'http:' && api.protocol !== 'https:')
    ) {
      return;
    }
    binding.apiBase = api.origin;
  } catch {
    return;
  }

  window.__MYRM_E2E_RUNTIME__ = Object.freeze(binding);
  window.__MYRM_E2E_API_BASE__ = binding.apiBase;

  // Collect client-side failures from the very first script into the sink the bridge diagnostics
  // read (`window.__MYRM_DIAG_ERRORS__`; the bridge wait reuses an existing sink). A hydration error
  // is raised long before the first bridge poll, so a sink installed by that poll would miss the
  // error that broke the boot and the timeout report would have no page error to show.
  window.__MYRM_DIAG_ERRORS__ = [];
  (() => {
    const sink = window.__MYRM_DIAG_ERRORS__;
    const push = (kind, msg) => {
      if (sink.length < 12) {
        sink.push(`${kind}: ${String(msg).slice(0, 240)}`);
      }
    };
    window.addEventListener('error', (e) => push('error', e.message || e.filename));
    window.addEventListener('unhandledrejection', (e) => push('rejection', e.reason?.message || e.reason));
  })();

  const routeHttpUrl = (value) => {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin) {
      return value;
    }
    if (!url.pathname.startsWith('/api/v1') && !url.pathname.startsWith('/webui')) {
      return value;
    }
    return `${binding.apiBase}${url.pathname}${url.search}${url.hash}`;
  };

  const nativeFetch = window.fetch.bind(window);
  const healthUrl = `${binding.apiBase}/api/v1/health`;
  const runtimeReady = nativeFetch(healthUrl, { cache: 'no-store' }).then(async (response) => {
    if (!response.ok) {
      throw new Error(`E2E_RUNTIME_HEALTH_HTTP_${response.status}`);
    }
    const payload = await response.json();
    if (payload.runtime_id !== binding.runtimeId) {
      throw new Error(`E2E_RUNTIME_MISMATCH expected=${binding.runtimeId} actual=${payload.runtime_id || '<missing>'}`);
    }
    window.dispatchEvent(new CustomEvent('myrm_e2e_runtime_ready', { detail: binding }));
    return binding;
  });
  window.__MYRM_E2E_RUNTIME_READY__ = runtimeReady;

  window.fetch = (input, init) => {
    if (input instanceof Request) {
      const routed = routeHttpUrl(input.url);
      if (routed === input.url) {
        return nativeFetch(input, init);
      }
      return runtimeReady.then(() => nativeFetch(new Request(routed, input), init));
    }
    const routed = routeHttpUrl(String(input));
    if (routed === input) {
      return nativeFetch(input, init);
    }
    return runtimeReady.then(() => nativeFetch(routed, init));
  };

  const xhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function open(method, url, ...rest) {
    return xhrOpen.call(this, method, routeHttpUrl(String(url)), ...rest);
  };

  const proxyUrlConstructor = (NativeConstructor, protocol) =>
    new Proxy(NativeConstructor, {
      construct(Target, args) {
        const [url, ...rest] = args;
        const routed = routeHttpUrl(String(url));
        const transportUrl = routed.startsWith('http') ? routed.replace(/^http/, protocol) : routed;
        return Reflect.construct(Target, [transportUrl, ...rest]);
      },
    });

  if (window.EventSource) {
    window.EventSource = proxyUrlConstructor(window.EventSource, 'http');
  }
  if (window.WebSocket) {
    window.WebSocket = proxyUrlConstructor(window.WebSocket, 'ws');
  }
})();
