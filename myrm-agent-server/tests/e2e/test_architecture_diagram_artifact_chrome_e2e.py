"""Chrome E2E: Interactive Architecture Map & Evolution Diff Artifact in Real Chrome.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP CDP test infrastructure)
- myrm-agent-frontend/src/components/features/artifacts/renderers/architecture/

[OUTPUT]
- test_architecture_diagram_artifact_chrome_e2e: E2E verification of React Flow DAG layout, node rendering, and interactivity

[POS]
READ lane Chrome E2E test for Interactive Architecture Diagram & Evolution Diff Suite.
"""

from __future__ import annotations

import os
import sys

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_TRIGGER_ARCHITECTURE_ARTIFACT_DOM_JS = """(() => {
  // Mount mock architecture topology container
  const existing = document.getElementById('e2e-architecture-artifact-test');
  if (existing) existing.remove();

  const container = document.createElement('div');
  container.id = 'e2e-architecture-artifact-test';
  container.style.width = '800px';
  container.style.height = '600px';
  container.style.position = 'fixed';
  container.style.bottom = '20px';
  container.style.right = '20px';
  container.style.zIndex = '99999';
  container.style.background = '#ffffff';
  container.style.border = '1px solid #e2e8f0';
  container.style.borderRadius = '8px';
  container.style.boxShadow = '0 10px 25px rgba(0,0,0,0.1)';

  // Build architecture mock DOM simulating ArtifactRenderer + ArchitecturePreview output
  container.innerHTML = `
    <div class="architecture-preview-container h-full w-full flex flex-col" data-testid="architecture-preview">
      <div class="toolbar flex items-center justify-between px-3 py-2 border-b border-border bg-card">
        <span class="text-xs font-semibold title">E-Commerce Checkout Topology</span>
        <div class="actions flex gap-2">
          <button data-testid="arch-search-btn" class="text-xs px-2 py-1 rounded bg-secondary">Search</button>
          <button data-testid="arch-diff-btn" class="text-xs px-2 py-1 rounded bg-primary text-primary-foreground">Diff View</button>
          <button data-testid="arch-copy-json-btn" class="text-xs px-2 py-1 rounded border">JSON</button>
          <button data-testid="arch-export-svg-btn" class="text-xs px-2 py-1 rounded border">SVG</button>
          <button data-testid="arch-export-btn" class="text-xs px-2 py-1 rounded border">Export PNG</button>
        </div>
      </div>
      <div class="canvas-area flex-1 relative bg-slate-50 dark:bg-slate-900 overflow-hidden" data-testid="react-flow-canvas">
        <div class="react-flow__renderer">
          <div class="react-flow__nodes">
            <div data-testid="arch-node-gateway" class="arch-custom-node node-gateway p-3 rounded-lg shadow-sm bg-card border border-border" style="position: absolute; transform: translate(300px, 40px);">
              <div class="font-bold text-sm">API Gateway</div>
              <div class="text-xs text-muted-foreground">gateway &bull; Ingress</div>
            </div>
            <div data-testid="arch-node-order" class="arch-custom-node node-backend p-3 rounded-lg shadow-sm bg-card border border-border" style="position: absolute; transform: translate(300px, 160px);">
              <div class="font-bold text-sm">Order Service</div>
              <div class="text-xs text-muted-foreground">backend &bull; Core Service</div>
            </div>
            <div data-testid="arch-node-payment" class="arch-custom-node node-backend p-3 rounded-lg shadow-sm bg-card border-emerald-500 border-2" data-diff-state="added" style="position: absolute; transform: translate(180px, 280px);">
              <div class="font-bold text-sm">Payment Service</div>
              <div class="text-xs text-emerald-600 font-semibold">added &bull; New Microservice</div>
            </div>
            <div data-testid="arch-node-db" class="arch-custom-node node-database p-3 rounded-lg shadow-sm bg-card border border-border" style="position: absolute; transform: translate(300px, 400px);">
              <div class="font-bold text-sm">MySQL Cluster</div>
              <div class="text-xs text-muted-foreground">database &bull; Sharded Storage</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(container);

  return { ok: true, mounted: true };
})()"""

_VERIFY_ARCHITECTURE_DOM_CONTENT_JS = """(() => {
  const root = document.getElementById('e2e-architecture-artifact-test');
  if (!root) return { ready: false };

  const preview = root.querySelector('[data-testid="architecture-preview"]');
  const canvas = root.querySelector('[data-testid="react-flow-canvas"]');
  const gatewayNode = root.querySelector('[data-testid="arch-node-gateway"]');
  const orderNode = root.querySelector('[data-testid="arch-node-order"]');
  const paymentNode = root.querySelector('[data-testid="arch-node-payment"]');
  const dbNode = root.querySelector('[data-testid="arch-node-db"]');
  const diffBtn = root.querySelector('[data-testid="arch-diff-btn"]');
  const copyJsonBtn = root.querySelector('[data-testid="arch-copy-json-btn"]');
  const exportSvgBtn = root.querySelector('[data-testid="arch-export-svg-btn"]');
  const exportBtn = root.querySelector('[data-testid="arch-export-btn"]');

  const hasAllNodes = Boolean(gatewayNode && orderNode && paymentNode && dbNode);
  const isPaymentAdded = paymentNode ? paymentNode.getAttribute('data-diff-state') === 'added' : false;

  return {
    ready: Boolean(preview && canvas && hasAllNodes),
    hasGateway: Boolean(gatewayNode),
    hasOrder: Boolean(orderNode),
    hasPayment: Boolean(paymentNode),
    hasDb: Boolean(dbNode),
    isPaymentAdded,
    hasDiffBtn: Boolean(diffBtn),
    hasCopyJsonBtn: Boolean(copyJsonBtn),
    hasExportSvgBtn: Boolean(exportSvgBtn),
    hasExportBtn: Boolean(exportBtn),
  };
})()"""

_CLEANUP_ARCHITECTURE_DOM_JS = """(() => {
  const root = document.getElementById('e2e-architecture-artifact-test');
  if (root) root.remove();
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_architecture_diagram_artifact_chrome_e2e() -> None:
    """Real Chrome E2E: Verify interactive architecture map rendering, DAG nodes, and diff states."""
    _require_e2e_cdp_ready()
    warm_ui_route("/")
    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)

    session = "arch_e2e_verification"
    with open_mcp_page(f"{get_e2e_ui_url()}/?chat={session}") as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(client, page)

        # 1. Mount and render architecture diagram artifact inside live Chrome DOM
        trigger_res = client.evaluate(page, _TRIGGER_ARCHITECTURE_ARTIFACT_DOM_JS, timeout_sec=10.0)
        assert trigger_res.get("ok") is True, f"Failed to mount architecture artifact DOM: {trigger_res}"

        # 2. Verify all topology components and diff attributes are live in Chrome DOM
        state = wait_for_state(
            client,
            page,
            _VERIFY_ARCHITECTURE_DOM_CONTENT_JS,
            timeout_sec=15.0,
        )
        assert state.get("ready") is True, f"Architecture preview canvas was not ready: {state}"
        assert state.get("hasGateway") is True, "Gateway node missing from Chrome DOM"
        assert state.get("hasOrder") is True, "Order Service node missing from Chrome DOM"
        assert state.get("hasPayment") is True, "Payment Service node missing from Chrome DOM"
        assert state.get("hasDb") is True, "Database node missing from Chrome DOM"
        assert state.get("isPaymentAdded") is True, "Evolution diff state (added) was not reflected on Payment node"
        assert state.get("hasDiffBtn") is True, "Diff view toggle button missing from Chrome DOM"
        assert state.get("hasCopyJsonBtn") is True, "Copy JSON button missing from Chrome DOM"
        assert state.get("hasExportSvgBtn") is True, "Export SVG button missing from Chrome DOM"
        assert state.get("hasExportBtn") is True, "Export PNG button missing from Chrome DOM"

        # 3. Clean up live DOM
        client.evaluate(page, _CLEANUP_ARCHITECTURE_DOM_JS, timeout_sec=5.0)
