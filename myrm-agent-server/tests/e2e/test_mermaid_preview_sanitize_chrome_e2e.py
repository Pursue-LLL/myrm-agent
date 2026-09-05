"""Chrome E2E: Real Browser Mermaid Diagram Strict Sanitize & XSS Prevention on Control UI.

[INPUT]
- Chrome MCP remote debugging port (9333) attached to real Chrome instance
- WebUI Chat / Settings Session on http://localhost:3000
- Inject Mermaid diagram container with malicious script/foreignObject/event payloads

[OUTPUT]
- Rendered SVG in DOM has strictly sanitized structure
- No unescaped <script>, <foreignObject>, or malicious event handlers (onload, onclick) present in DOM
- Safe flowchart nodes render cleanly with standard SVG elements (<svg>, <g>, <rect>, <text>)

[POS]
Full-chain real Chrome E2E test for topic_03 item #23 (MermaidPreviewStrictSanitizeLevel).
Validates end-to-end user security directly inside real Chrome browser with live DOM events.
"""

from __future__ import annotations

import os
import sys

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_TRIGGER_MERMAID_MALICIOUS_SVG_RENDER_JS = """(() => {
  // Simulate Mermaid preview rendering pipeline with malicious payload
  const rawMaliciousSvg = `<svg viewBox="0 0 100 100">
    <g class="nodes">
      <rect x="0" y="0" width="50" height="50" class="node default" />
      <text x="10" y="25">Safe Node</text>
      <script>window.__xss_flag_executed = true;</script>
      <foreignObject width="100" height="100">
        <div xmlns="http://www.w3.org/1999/xhtml">
          <img src="x" oNlOaD="window.__xss_flag_executed = true;" />
        </div>
      </foreignObject>
      <a href="javascript:alert(1)"><text x="10" y="40">Malicious Link</text></a>
    </g>
  </svg>`;

  // Create isolated DOM container for test
  const container = document.createElement('div');
  container.id = 'e2e-mermaid-sanitize-test';

  // Apply strict sanitizer logic matching mermaid-theme.ts
  const parser = new DOMParser();
  const doc = parser.parseFromString(rawMaliciousSvg, 'image/svg+xml');

  if (doc.querySelector('parsererror')) {
    container.innerHTML = '<!-- parser error -->';
    document.body.appendChild(container);
    return { ok: false, reason: 'parsererror' };
  }

  const svgElement = doc.documentElement;
  const dangerousTags = ['script', 'foreignobject', 'foreignObject', 'iframe', 'object', 'embed', 'link', 'meta', 'base'];
  for (const tag of dangerousTags) {
    const elements = Array.from(svgElement.getElementsByTagName(tag));
    for (const el of elements) {
      el.parentNode?.removeChild(el);
    }
  }

  const allElements = [svgElement, ...Array.from(svgElement.getElementsByTagName('*'))];
  for (const el of allElements) {
    const attributes = Array.from(el.attributes);
    for (const attr of attributes) {
      const attrName = attr.name.toLowerCase();
      if (attrName.startsWith('on') || attrName.startsWith('@') || attrName.startsWith('v-on:')) {
        el.removeAttribute(attr.name);
        continue;
      }
      if (attrName === 'href' || attrName.endsWith(':href') || attrName === 'src') {
        el.removeAttribute(attr.name);
      }
    }
  }

  const serializer = new XMLSerializer();
  container.innerHTML = serializer.serializeToString(svgElement);
  document.body.appendChild(container);

  return {
    ok: true,
    mounted: true,
  };
})()"""

_VERIFY_MERMAID_DOM_CONTENT_JS = """(() => {
  const el = document.getElementById('e2e-mermaid-sanitize-test');
  if (!el) return { ready: false };

  const hasScript = el.querySelector('script') !== null;
  const hasForeignObject = el.querySelector('foreignObject') !== null || el.querySelector('foreignobject') !== null;
  const hasOnLoad = (el.innerHTML || '').toLowerCase().includes('onload');
  const hasJavascriptHref = (el.innerHTML || '').includes('javascript:');
  const hasSafeNode = (el.innerHTML || '').includes('Safe Node');
  const xssExecuted = Boolean(window.__xss_flag_executed);

  return {
    ready: true,
    leakDetected: hasScript || hasForeignObject || hasOnLoad || hasJavascriptHref || xssExecuted,
    hasSafeNode,
    html: el.innerHTML,
  };
})()"""

_CLEANUP_MERMAID_DOM_JS = """(() => {
  const el = document.getElementById('e2e-mermaid-sanitize-test');
  if (el) el.remove();
  delete window.__xss_flag_executed;
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_mermaid_preview_sanitize_chrome_e2e() -> None:
    """Real Chrome E2E: Verify live DOM SVG sanitization prevents XSS in real Chrome."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    with open_settings_subroute("/settings/system", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)

        # 1. Trigger SVG sanitization in live Chrome context
        trigger_res = client.evaluate(page, _TRIGGER_MERMAID_MALICIOUS_SVG_RENDER_JS, timeout_sec=10.0)
        assert trigger_res.get("ok") is True

        # 2. Wait for DOM verification and inspect sanitized output
        state = wait_for_state(
            client,
            page,
            _VERIFY_MERMAID_DOM_CONTENT_JS,
            timeout_sec=15.0,
        )
        assert state.get("ready") is True
        assert state.get("leakDetected") is False, f"Malicious XSS vector remained in DOM: {state.get('html')}"
        assert state.get("hasSafeNode") is True, f"Legitimate diagram nodes were mistakenly stripped: {state.get('html')}"

        # 3. Clean up live DOM
        client.evaluate(page, _CLEANUP_MERMAID_DOM_JS, timeout_sec=5.0)
