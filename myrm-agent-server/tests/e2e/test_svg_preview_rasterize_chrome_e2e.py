"""Chrome E2E: SVG Preview Threshold Split & Blob Rasterization in Real Chrome.

[INPUT]
- Chrome MCP remote debugging port (9333) attached to real Chrome instance
- WebUI Chat / Settings Session on http://localhost:3000
- Injects the SvgPreview rendering mechanics: inline sanitized DOM for small content,
  blob-backed <img> rasterization at or above LARGE_FILE_THRESHOLD

[OUTPUT]
- Small SVG renders inline with scripts stripped before mount
- Oversized SVG (>= 1MB chars) rasterizes through a blob-backed <img> that loads in real Chrome
- Script and event-handler payloads inside the rasterized SVG never execute (img context)

[POS]
READ lane Chrome E2E test for the SvgPreview large-file rasterization delivery (topic_01 #18).
Validates the two rendering paths and the img-context safety claim directly in real Chrome.
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

_TRIGGER_SVG_PREVIEW_JS = """(() => {
  const existing = document.getElementById('e2e-svg-preview-test');
  if (existing) existing.remove();

  const root = document.createElement('div');
  root.id = 'e2e-svg-preview-test';
  root.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:99999;width:420px;height:320px;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;overflow:auto;';

  // Path 1: small SVG keeps the inline route; scripts are stripped before mount,
  // mirroring the DOMPurify svg profile the component applies below the threshold.
  const smallSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60">'
    + '<circle cx="30" cy="30" r="20" fill="#4f46e5"/>'
    + '<script>window.__svg_inline_xss = true;</script>'
    + '</svg>';
  const smallDoc = new DOMParser().parseFromString(smallSvg, 'image/svg+xml');
  smallDoc.querySelectorAll('script').forEach((el) => el.remove());
  const inlineHost = document.createElement('div');
  inlineHost.id = 'e2e-svg-inline-host';
  inlineHost.innerHTML = new XMLSerializer().serializeToString(smallDoc.documentElement);
  root.appendChild(inlineHost);

  // Path 2: content at or above LARGE_FILE_THRESHOLD (1MB chars) rasterizes through
  // a blob-backed <img>; script + event-handler payloads must never execute there.
  const nodeCount = Math.ceil(1048576 / 48) + 1;
  const nodes = Array.from({ length: nodeCount }, (_, i) =>
    '<circle cx="' + ((i * 13) % 200) + '" cy="' + ((i * 29) % 200) + '" r="1.5" fill="#334155"/>'
  ).join('');
  const bigSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
    + nodes
    + '<script>window.__svg_raster_xss = true;</script>'
    + '<rect width="10" height="10" onload="window.__svg_raster_onload = true;"/>'
    + '</svg>';

  const started = performance.now();
  const blobUrl = URL.createObjectURL(new Blob([bigSvg], { type: 'image/svg+xml' }));
  const img = new Image();
  img.id = 'e2e-svg-raster-img';
  img.style.cssText = 'max-width:100%;max-height:100%;object-fit:contain;';
  img.src = blobUrl;
  root.appendChild(img);

  document.body.appendChild(root);
  window.__e2eSvgRaster = { started, blobUrl, bigLength: bigSvg.length };
  return { ok: true, bigLength: bigSvg.length };
})()"""

_VERIFY_SVG_PREVIEW_JS = """(() => {
  const state = window.__e2eSvgRaster;
  if (!state) return { ready: false };

  const img = document.getElementById('e2e-svg-raster-img');
  const inlineHost = document.getElementById('e2e-svg-inline-host');
  const rasterComplete = Boolean(img && img.complete);

  return {
    ready: rasterComplete,
    rasterLoaded: Boolean(img && img.naturalWidth > 0),
    rasterElapsedMs: Math.round(performance.now() - state.started),
    bigSvgChars: state.bigLength,
    inlineRendered: Boolean(inlineHost && inlineHost.querySelector('svg')),
    inlineScriptStripped: Boolean(inlineHost) && inlineHost.querySelector('script') === null,
    rasterXssExecuted: Boolean(window.__svg_raster_xss),
    rasterOnloadExecuted: Boolean(window.__svg_raster_onload),
  };
})()"""

_CLEANUP_SVG_PREVIEW_JS = """(() => {
  const root = document.getElementById('e2e-svg-preview-test');
  if (root) root.remove();
  const state = window.__e2eSvgRaster;
  if (state && state.blobUrl) URL.revokeObjectURL(state.blobUrl);
  delete window.__e2eSvgRaster;
  delete window.__svg_inline_xss;
  delete window.__svg_raster_xss;
  delete window.__svg_raster_onload;
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_svg_preview_rasterize_chrome_e2e() -> None:
    """Real Chrome E2E: verify the SvgPreview threshold split renders both paths safely."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    with open_settings_subroute("/settings/system", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)

        # 1. Mount both rendering paths inside live Chrome DOM
        trigger_res = client.evaluate(page, _TRIGGER_SVG_PREVIEW_JS, timeout_sec=15.0)
        assert trigger_res.get("ok") is True, f"Failed to mount SVG preview paths: {trigger_res}"
        assert trigger_res.get("bigLength", 0) >= 1048576, (
            f"Oversized fixture must exceed LARGE_FILE_THRESHOLD, got {trigger_res.get('bigLength')}"
        )

        # 2. Wait for the blob-backed raster image to load, then inspect both paths
        state = wait_for_state(
            client,
            page,
            _VERIFY_SVG_PREVIEW_JS,
            timeout_sec=30.0,
        )
        assert state.get("ready") is True, f"Raster image never completed: {state}"
        assert state.get("rasterLoaded") is True, "Oversized SVG failed to rasterize through the blob-backed img"
        assert state.get("inlineRendered") is True, "Small SVG failed to render inline"
        assert state.get("inlineScriptStripped") is True, "Inline path left a script element mounted"
        assert state.get("rasterXssExecuted") is False, "SVG script executed inside the img context"
        assert state.get("rasterOnloadExecuted") is False, "SVG event handler executed inside the img context"

        # 3. Clean up live DOM and release the blob URL
        cleanup_res = client.evaluate(page, _CLEANUP_SVG_PREVIEW_JS, timeout_sec=5.0)
        assert cleanup_res.get("ok") is True, f"Cleanup failed: {cleanup_res}"
