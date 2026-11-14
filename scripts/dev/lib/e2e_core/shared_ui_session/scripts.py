"""Browser-side scripts of the shared UI session contract: window-global reset, private-search hydrate,
empty search block and bridge-ready probe."""

from __future__ import annotations

RESET_GLOBALS_JS = """(() => {
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  window.__MYRM_E2E_SEND_GENERATION__ = (window.__MYRM_E2E_SEND_GENERATION__ ?? 0) + 1;
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.abortActiveStream?.();
  bridge?.releaseActiveStreamForApiResume?.();
  bridge?.clearSseSnapshot?.();
  return { ok: true, phase: 'RESET_GLOBALS' };
})()"""

RESET_GLOBALS_KEEP_SEARCH_BLOCK_JS = """(() => {
  window.__MYRM_E2E_SEND_GENERATION__ = (window.__MYRM_E2E_SEND_GENERATION__ ?? 0) + 1;
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.abortActiveStream?.();
  bridge?.releaseActiveStreamForApiResume?.();
  bridge?.clearSseSnapshot?.();
  return { ok: true, phase: 'RESET_GLOBALS', searchBlockPreserved: Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__) };
})()"""

HYDRATE_PRIVATE_SEARCH_JS = """(async () => {
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  // BRIDGE_READY may pass, then a parallel warm-shell reclaim / navigate can
  // reload the page and momentarily drop __MYRM_E2E_CHAT__ before React remounts
  // the bridge. Fail-fast on a transient no-bridge strands the SEARCH_POLICY
  // contract; instead poll for the bridge inside the deadline like BRIDGE_READY.
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const liveBridge = window.__MYRM_E2E_CHAT__;
    if (liveBridge?.syncSearchServicesFromE2eApi) {
      const sync = await liveBridge.syncSearchServicesFromE2eApi();
      if (sync?.ok) {
        return { ok: true, count: sync.count, phase: 'SEARCH_POLICY' };
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  const finalBridge = window.__MYRM_E2E_CHAT__;
  if (!finalBridge?.syncSearchServicesFromE2eApi) {
    return { ok: false, err: 'no-bridge', phase: 'SEARCH_POLICY' };
  }
  return { ok: false, err: 'empty-search-configs', phase: 'SEARCH_POLICY' };
})()"""

SET_EMPTY_SEARCH_BLOCK_JS = """(() => {
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  return { ok: true, phase: 'SEARCH_POLICY' };
})()"""

BRIDGE_READY_PROBE_JS = """(() => ({
  hasBridge: Boolean(window.__MYRM_E2E_CHAT__),
  hasSendChatMessage: typeof window.__MYRM_E2E_CHAT__?.sendChatMessage === 'function',
  hasSubmitAndObserveTurn:
    typeof window.__MYRM_E2E_CHAT__?.submitAndObserveTurn === 'function',
  hasAttach: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
  hasProgressSnap:
    typeof window.__MYRM_E2E_CHAT__?.getFastSearchProgressSnapshot === 'function',
  blockSearchSync: Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__),
  phase: 'BRIDGE_READY',
}))()"""
