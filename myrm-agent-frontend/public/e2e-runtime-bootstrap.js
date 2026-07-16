(() => {
  'use strict';

  const PREFIX = 'myrm-e2e-v1:';
  const raw = window.name;
  if (!raw.startsWith(PREFIX)) return;

  const isLoopback = (hostname) => hostname === '127.0.0.1' || hostname === 'localhost';
  const isIdentifier = (value) =>
    typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(value);

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

  const routeHttpUrl = (value) => {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin) return value;
    if (!url.pathname.startsWith('/api/v1') && !url.pathname.startsWith('/webui')) {
      return value;
    }
    return `${binding.apiBase}${url.pathname}${url.search}${url.hash}`;
  };

  const nativeFetch = window.fetch.bind(window);
  const healthUrl = `${binding.apiBase}/api/v1/health`;
  const runtimeReady = nativeFetch(healthUrl, { cache: 'no-store' })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`E2E_RUNTIME_HEALTH_HTTP_${response.status}`);
      }
      const payload = await response.json();
      if (payload.runtime_id !== binding.runtimeId) {
        throw new Error(
          `E2E_RUNTIME_MISMATCH expected=${binding.runtimeId} actual=${payload.runtime_id || '<missing>'}`,
        );
      }
      return binding;
    });
  window.__MYRM_E2E_RUNTIME_READY__ = runtimeReady;

  window.fetch = (input, init) => {
    if (input instanceof Request) {
      const routed = routeHttpUrl(input.url);
      if (routed === input.url) return nativeFetch(input, init);
      return runtimeReady.then(() => nativeFetch(new Request(routed, input), init));
    }
    const routed = routeHttpUrl(String(input));
    if (routed === input) return nativeFetch(input, init);
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
        const transportUrl = routed.startsWith('http')
          ? routed.replace(/^http/, protocol)
          : routed;
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
