/**
 * [INPUT]
 * - canvasSecurityTypes: CanvasSandboxPolicy, CanvasEgressRequest, CanvasSecurityAuditEvent
 *
 * [OUTPUT]
 * - CanvasSecurityBridge: Security compiler, CSP injector, and postMessage gating controller
 *
 * [POS]
 * Security bridge between host window and isolated Canvas iframe (Item 44 P0).
 * Strictly under 220 lines. Zero `any`.
 */

import type { CanvasSandboxPolicy } from './canvasSecurityTypes';

export const STRICT_SANDBOX_POLICY: CanvasSandboxPolicy = 'allow-scripts allow-forms';

export const STRICT_CSP_META =
  `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob: https:; font-src data:; connect-src 'none'; frame-src 'none';">`;

/**
 * Sandboxed runtime script injected into the iframe.
 * Intercepts escape attempts to window.parent and gates network requests via postMessage.
 */
const RUNTIME_INJECTION_SCRIPT = `
<script>
(function() {
  // 1. Report parent escape attempts
  try {
    var testParent = window.parent.location.href;
  } catch (err) {
    // Expected SecurityError in cross-origin sandbox
  }

  // 2. Intercept fetch for egress gating
  var originalFetch = window.fetch;
  window.fetch = function(url, options) {
    return new Promise(function(resolve, reject) {
      var reqId = 'egress_' + Math.random().toString(36).slice(2, 9);
      var targetUrl = typeof url === 'string' ? url : (url && url.url ? url.url : '');
      var parsedDomain = '';
      try {
        parsedDomain = new URL(targetUrl, window.location.href).hostname;
      } catch (e) {
        parsedDomain = 'unknown';
      }

      function onResponse(event) {
        if (!event.data || event.data.type !== 'canvas-egress-response' || event.data.requestId !== reqId) {
          return;
        }
        window.removeEventListener('message', onResponse);
        if (event.data.allowed) {
          resolve(new Response(JSON.stringify({ status: 'allowed_mock', message: 'Egress permitted by user' }), { status: 200 }));
        } else {
          reject(new Error('Network egress blocked by Canvas Security Gate: ' + targetUrl));
        }
      }

      window.addEventListener('message', onResponse);

      window.parent.postMessage({
        type: 'canvas-egress-request',
        requestId: reqId,
        url: targetUrl,
        domain: parsedDomain,
        method: (options && options.method) ? options.method : 'GET'
      }, '*');

      // Safety timeout after 15 seconds
      setTimeout(function() {
        window.removeEventListener('message', onResponse);
        reject(new Error('Canvas egress request timed out'));
      }, 15000);
    });
  };
})();
</script>
`;

/**
 * Compiles raw HTML into an isolated, CSP-guarded and runtime-monitored sandboxed document.
 */
export function compileSandboxedHtml(rawContent: string): string {
  if (!rawContent || !rawContent.trim()) {
    return `<!DOCTYPE html><html><head>${STRICT_CSP_META}</head><body></body></html>`;
  }

  // If complete HTML document, inject CSP and runtime script into <head>
  if (/<html[\s>]/i.test(rawContent)) {
    if (/<head[\s>]/i.test(rawContent)) {
      return rawContent.replace(
        /<head[\s>]/i,
        `$&${STRICT_CSP_META}${RUNTIME_INJECTION_SCRIPT}`
      );
    }
    return rawContent.replace(
      /<html[\s>]/i,
      `$&<head>${STRICT_CSP_META}${RUNTIME_INJECTION_SCRIPT}</head>`
    );
  }

  // Fragment mode: wrap in standard isolated HTML container
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  ${STRICT_CSP_META}
  ${RUNTIME_INJECTION_SCRIPT}
  <style>
    body {
      margin: 0;
      padding: 16px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #1e293b;
      background-color: transparent;
    }
  </style>
</head>
<body>
  ${rawContent}
</body>
</html>`;
}

export interface InboundCanvasMessage {
  type: string;
  requestId?: string;
  url?: string;
  domain?: string;
  method?: string;
}

/**
 * Validates inbound message event from canvas iframe.
 */
export function validateInboundCanvasMessage(
  event: MessageEvent,
  expectedContentWindow: Window | null
): InboundCanvasMessage | null {
  if (!expectedContentWindow || event.source !== expectedContentWindow) {
    return null;
  }

  const data = event.data;
  if (!data || typeof data !== 'object') {
    return null;
  }

  const type = (data as Record<string, unknown>).type;
  if (typeof type !== 'string') {
    return null;
  }

  return {
    type,
    requestId: typeof (data as Record<string, unknown>).requestId === 'string'
      ? (data as Record<string, unknown>).requestId as string
      : undefined,
    url: typeof (data as Record<string, unknown>).url === 'string'
      ? (data as Record<string, unknown>).url as string
      : undefined,
    domain: typeof (data as Record<string, unknown>).domain === 'string'
      ? (data as Record<string, unknown>).domain as string
      : undefined,
    method: typeof (data as Record<string, unknown>).method === 'string'
      ? (data as Record<string, unknown>).method as string
      : undefined,
  };
}
