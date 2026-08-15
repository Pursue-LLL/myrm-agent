"""Chrome E2E (SHARED): Connect Wizard Agent Plugins bundle zip download.

Walks the real user flow in the browser on /settings/memory:

1. Switch to the Verify section and open the Connect Wizard.
2. Generate an Agent Plugins bundle against the real backend API.
3. Click "Download All (.zip)" and assert the browser receives a
   `myrm-memory[-<agent>].zip` download signal via the real `a[download]` path.

The download signal is captured with an HTMLAnchorElement click patch so the
E2E verifies the UI wired the correct filename without polluting the download
directory (no browser-level file write).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_OPEN_CONNECT_WIZARD_JS = """(() => {
  const findBtn = (re) => Array.from(document.querySelectorAll('button')).find(
    (el) => re.test((el.textContent || '').trim()),
  );
  const verifyBtn = findBtn(/^(Verify|验证)$/);
  if (!verifyBtn) {
    return { ready: false, clicked: false, why: 'no Verify/验证 section button',
             text: (document.body?.textContent || '').slice(0, 700) };
  }
  verifyBtn.click();
  const connectBtn = findBtn(/^Connect$/);
  if (!connectBtn) {
    return { ready: false, clicked: false, why: 'no Connect button',
             text: (document.body?.textContent || '').slice(0, 700) };
  }
  connectBtn.click();
  return { ready: true, clicked: true };
})()"""

_DIALOG_GENERATE_BTN_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Generate Agent Plugins bundle|生成 Agent Plugins 插件/.test(el.textContent || ''),
  );
  return { ready: !!btn, hasBtn: !!btn, text: text.slice(0, 800) };
})()"""

_INSTALL_DOWNLOAD_PATCH_JS = """(() => {
  if (window.__myrmDownloadPatchInstalled) {
    return { installed: true, downloads: window.__myrmDownloads };
  }
  window.__myrmDownloads = [];
  const orig = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.download) {
      window.__myrmDownloads.push(this.download);
      return;
    }
    return orig.call(this);
  };
  window.__myrmDownloadPatchInstalled = true;
  return { installed: true, downloads: window.__myrmDownloads };
})()"""

_CLICK_GENERATE_BUNDLE_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Generate Agent Plugins bundle|生成 Agent Plugins 插件/.test(el.textContent || ''),
  );
  if (!btn || btn.disabled) return { ready: false, clicked: false, disabled: btn?.disabled ?? null };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_DOWNLOAD_ALL_BTN_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Download All \\(.zip\\)|下载全部 \\(.zip\\)/.test(el.textContent || ''),
  );
  return { ready: !!btn, hasBtn: !!btn, text: text.slice(0, 1200) };
})()"""

_CLICK_DOWNLOAD_ALL_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Download All \\(.zip\\)|下载全部 \\(.zip\\)/.test(el.textContent || ''),
  );
  if (!btn || btn.disabled) return { ready: false, clicked: false, disabled: btn?.disabled ?? null };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_DOWNLOAD_SIGNAL_READY_JS = """(() => {
  const downloads = window.__myrmDownloads || [];
  const hits = downloads.filter((name) => /^myrm-memory/.test(name) && name.endsWith('.zip'));
  return { ready: hits.length > 0, downloads, hits };
})()"""


@contextmanager
def _connect_wizard_open() -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        opened = wait_for_state(client, page, _OPEN_CONNECT_WIZARD_JS, timeout_sec=90.0)
        print(f"[connect-wizard-e2e] opened={opened}", flush=True)
        assert opened.get("clicked") is True, opened
        dialog = wait_for_state(client, page, _DIALOG_GENERATE_BTN_READY_JS, timeout_sec=60.0)
        print(f"[connect-wizard-e2e] dialog={dialog}", flush=True)
        assert dialog.get("ready") is True, dialog
        yield client, page


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_connect_wizard_plugin_bundle_zip_download_chrome_e2e() -> None:
    """Real user flow: generate the Agent Plugins bundle and download it as zip."""
    with _connect_wizard_open() as (client, page):
        patched = client.evaluate(page, _INSTALL_DOWNLOAD_PATCH_JS)
        assert patched.get("installed") is True, patched

        generated = wait_for_state(client, page, _CLICK_GENERATE_BUNDLE_JS, timeout_sec=30.0)
        assert generated.get("clicked") is True, generated

        zip_btn = wait_for_state(client, page, _DOWNLOAD_ALL_BTN_READY_JS, timeout_sec=90.0)
        assert zip_btn.get("ready") is True, zip_btn

        clicked = wait_for_state(client, page, _CLICK_DOWNLOAD_ALL_JS, timeout_sec=30.0)
        assert clicked.get("clicked") is True, clicked

        signal = wait_for_state(client, page, _DOWNLOAD_SIGNAL_READY_JS, timeout_sec=60.0)
        assert signal.get("ready") is True, signal
        assert len(signal.get("hits", [])) >= 1, signal
        print(f"[connect-wizard-e2e] captured download names: {signal.get('downloads')}")
