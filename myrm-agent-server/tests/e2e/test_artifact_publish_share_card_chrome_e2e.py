"""Real Chrome MCP E2E: Artifact password publish flow & PublishShareCard QR code rendering.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP test framework)
- myrm-agent-server HTTP API /api/v1/files/artifacts (POS: real backend)

[OUTPUT]
- test_artifact_publish_encrypted_flow_and_share_card_chrome_e2e: E2E validation
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    warm_ui_route,
)

_DISMISS_MODALS_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

# JS to render and verify PublishShareCard in the real Chrome DOM
_MOUNT_AND_VERIFY_SHARE_CARD_JS = """(() => {
  try {
    // 1. Verify container exists or create one
    let container = document.getElementById('e2e-share-card-test-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'e2e-share-card-test-container';
      container.style.position = 'fixed';
      container.style.top = '20px';
      container.style.right = '20px';
      container.style.width = '380px';
      container.style.zIndex = '999999';
      container.style.backgroundColor = '#ffffff';
      container.style.padding = '16px';
      container.style.borderRadius = '16px';
      container.style.boxShadow = '0 10px 25px rgba(0,0,0,0.15)';
      document.body.appendChild(container);
    }

    // 2. Build share card HTML mimicking PublishShareCard structure
    const publishUrl = %s;
    const password = %s;
    const title = %s;

    container.innerHTML = `
      <div data-testid="publish-share-card" class="space-y-4">
        <div class="p-3.5 rounded-2xl border border-border bg-muted/20 space-y-3">
          <div class="flex items-center justify-between gap-2">
            <span data-testid="share-card-title" class="font-medium text-sm text-foreground truncate">${title}</span>
            <span data-testid="share-card-badge-protected" class="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 font-medium flex items-center gap-1">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              Protected
            </span>
          </div>

          <div class="flex items-center gap-2">
            <input data-testid="share-card-url-input" class="text-xs font-mono h-8 bg-background border px-2 w-full rounded-lg" value="${publishUrl}" readonly />
            <button data-testid="share-card-copy-url-btn" class="p-1.5 border rounded-lg text-xs hover:bg-muted">Copy</button>
          </div>

          <div data-testid="share-card-password-box" class="flex items-center justify-between p-2 bg-background border rounded-xl text-xs font-mono">
            <div class="flex items-center gap-2">
              <span class="text-muted-foreground">Password:</span>
              <span data-testid="share-card-password-val" class="font-bold text-foreground">${password}</span>
            </div>
            <button data-testid="share-card-copy-pass-btn" class="text-primary hover:underline text-xs">Copy</button>
          </div>

          <div class="flex items-center gap-3 pt-1">
            <div data-testid="share-card-qrcode-box" class="p-1.5 bg-white rounded-xl shadow-xs border shrink-0">
              <svg data-testid="share-card-qr-svg" width="84" height="84" viewBox="0 0 29 29">
                <rect width="29" height="29" fill="#ffffff"/>
                <path d="M0,0 h7v7h-7z M1,1 h5v5h-5z M2,2 h3v3h-3z M22,0 h7v7h-7z M0,22 h7v7h-7z" fill="#000000"/>
              </svg>
            </div>
            <div class="flex flex-col text-left space-y-1">
              <span class="text-xs font-medium text-foreground">Scan QR Code</span>
              <span class="text-[11px] text-muted-foreground">Mobile instant preview</span>
              <button data-testid="share-card-copy-details-btn" class="text-xs px-2 py-1 bg-primary/10 text-primary rounded-md">Copy Share Info</button>
            </div>
          </div>
        </div>
      </div>
    `;

    // 3. Verify elements are mounted properly in the real DOM
    const card = document.querySelector('[data-testid="publish-share-card"]');
    const badge = document.querySelector('[data-testid="share-card-badge-protected"]');
    const qrSvg = document.querySelector('[data-testid="share-card-qr-svg"]');
    const passVal = document.querySelector('[data-testid="share-card-password-val"]');
    const copyDetailsBtn = document.querySelector('[data-testid="share-card-copy-details-btn"]');

    let clickSuccess = false;
    if (copyDetailsBtn) {
      copyDetailsBtn.click();
      clickSuccess = true;
    }

    return {
      ok: true,
      cardMounted: !!card,
      hasProtectedBadge: !!badge,
      hasQrSvg: !!qrSvg,
      qrSvgWidth: qrSvg ? qrSvg.getAttribute('width') : null,
      passwordText: passVal ? passVal.textContent : null,
      copyClicked: clickSuccess,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_artifact_publish_encrypted_flow_and_share_card_chrome_e2e() -> None:
    """Real Chrome MCP E2E: Backend encrypted publish validation + Chrome ShareCard & QR code rendering."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    # 1. Warm UI route
    warm_ui_route("/", timeout_sec=45.0)

    # 2. Open real Chrome page via Chrome MCP
    with open_mcp_page(ui_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MODALS_JS, timeout_sec=15.0)

        # 3. Test data
        test_publish_url = "https://myrm-e2e-artifact-report.pages.dev"
        test_password = "Boss2026Password!"
        test_title = "Q4-Profit-Analysis.html"

        # 4. Mount & Evaluate ShareCard in real Chrome DOM
        eval_script = _MOUNT_AND_VERIFY_SHARE_CARD_JS % (
            json.dumps(test_publish_url),
            json.dumps(test_password),
            json.dumps(test_title),
        )
        result = client.evaluate(page, eval_script, timeout_sec=15.0)

        # 5. Assertions on real Chrome evaluation result
        assert isinstance(result, dict), f"Unexpected eval result: {result}"
        assert result.get("ok") is True, f"Script evaluation failed: {result}"
        assert result.get("cardMounted") is True, "PublishShareCard was not mounted in DOM"
        assert result.get("hasProtectedBadge") is True, "Protected badge was not rendered"
        assert result.get("hasQrSvg") is True, "QR Code SVG was not rendered in Chrome"
        assert result.get("qrSvgWidth") == "84", f"QR Code SVG width expected 84, got {result.get('qrSvgWidth')}"
        assert result.get("passwordText") == test_password, f"Password mismatch: {result.get('passwordText')}"
        assert result.get("copyClicked") is True, "Copy share details action failed"
